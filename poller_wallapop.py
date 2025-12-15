import json
from datetime import datetime, timezone
import time
from statistics import mean, median, stdev
import os
import sys
import requests

if os.name == "nt":
    os.system("chcp 65001 >nul")
    sys.stdout.reconfigure(encoding='utf-8')

# --- CONFIGURACIÓN ---
URL = "https://api.wallapop.com/api/v3/search"
HEADERS = {
    "Host": "api.wallapop.com",
    "X-DeviceOS": "0"
}

ES_URL = "http://elasticsearch:9200"
INDEX_NAME = "wallapop-motos"

# --- FUNCIONES BÁSICAS ---

def get_daily_filename():
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"wallapop_motos_{today}.json"

def load_existing_ids(filename):
    existing_ids = set()
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        if item_id := item.get("id"):
                            existing_ids.add(item_id)
        except Exception:
            pass
    return existing_ids

# --- DESCARGA SIN COORDENADAS → TODA ESPAÑA ---

def fetch_all_pages(keywords, category_id):
    all_items = []
    offset = 0
    limit = 50

    while True:
        params = {
            "source": "search_box",
            "keywords": keywords,
            "category_id": str(category_id),
            "time_filter": "today",
            "order_by": "newest",
            "offset": offset,
            "limit": limit
        }

        try:
            response = requests.get(URL, params=params, headers=HEADERS, timeout=15)
            response.raise_for_status()
            data = response.json()

            items = data.get("data", {}).get("section", {}).get("payload", {}).get("items", [])

            if not items:
                break

            all_items.extend(items)

            if len(items) < limit:
                break

            offset += limit
            time.sleep(0.5)

        except Exception:
            break

    return all_items

def remove_duplicates(items):
    seen_ids = set()
    unique_items = []
    duplicates_removed = 0

    for item in items:
        item_id = item.get("id")
        if item_id and item_id not in seen_ids:
            seen_ids.add(item_id)
            unique_items.append(item)
        else:
            duplicates_removed += 1

    return unique_items, duplicates_removed

def save_daily_file(all_items, filename):
    with open(filename, "a", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


# --- FILTRO INDUMENTARIA ---

def is_clothing_or_personal_gear(item):
    title = item.get("title", "").lower()
    description = item.get("description", "").lower()

    CLOTHING_KEYWORDS = [
        "casco", "guante", "chaqueta", "pantalón", "pantalon", "botas",
        "espaliers", "espalda", "goretex", "chamarra", "bota", "mono",
        "traje", "talla", "alforja", "mochila", "maleta", "chaleco",
        "protector", "protección", "impermeable", "capa de lluvia", "zapatos",
        "herramientas", "candado", "antirrobo", "cubremanos",
        "intercomunicador", "interfono", "bluetooth", "manoplas",
        "puños calefactables", "retrovisor", "aceite", "baúl", "pantalla"
    ]

    if any(keyword in title for keyword in CLOTHING_KEYWORDS):
        return True
    if any(keyword in description for keyword in CLOTHING_KEYWORDS):
        return True

    return False

def filter_clothing_items(items):
    filtered_items = []
    removed_count = 0
    for item in items:
        if not is_clothing_or_personal_gear(item):
            filtered_items.append(item)
        else:
            removed_count += 1

    return filtered_items, removed_count


# --- RIESGO ---

def detect_suspicious_keywords(text):
    RISK_CATEGORIES = {
        "CRITICAL_LEGAL": [
            "sin papeles", "sin documentacion", "sin documento", "no papeles",
            "papeles pendientes", "transferencia pendiente"
        ],
        "CRITICAL_INTEGRITY": [
            "sin itv", "no itv", "itv caducada",
            "para piezas", "despiece", "solo piezas",
            "km desconocidos", "kilometraje desconocido"
        ],
        "CRITICAL_FRAUD": [
            "robo", "importacion", "importada",
            "procedencia dudosa", "encontrada"
        ],
        "GENERAL_URGENCY": [
            "urgente", "solo hoy", "solo esta semana",
            "rápido", "venta rapida"
        ],
        "GENERAL_PRICE_BASED": [
            "ganga", "muy barato", "chollo", "oferta"
        ],
    }

    if not text:
        return [], set()

    text_lower = text.lower()
    found_keywords = []
    found_categories = set()

    for category, keywords in RISK_CATEGORIES.items():
        for keyword in keywords:
            if keyword in text_lower:
                found_keywords.append(keyword)
                found_categories.add(category)

    return found_keywords, found_categories

def calculate_relative_price_index(price, all_prices):
    if not all_prices or not price:
        return 1.0

    avg_price = mean(all_prices)
    if avg_price == 0:
        return 1.0

    return round(price / avg_price, 2)

def calculate_risk_score(item, all_prices, seller_items_count, found_categories, text_lower):
    score = 0

    if ("CRITICAL_LEGAL" in found_categories or
        "CRITICAL_INTEGRITY" in found_categories or
        "CRITICAL_FRAUD" in found_categories):
        score += 30

    if ("GENERAL_URGENCY" in found_categories or
        "GENERAL_PRICE_BASED" in found_categories):
        score += 15

    if all_prices:
        avg_price = mean(all_prices)
        price = item.get("price", {}).get("amount")

        if price:
            if price < avg_price * 0.4:
                score += 40
            elif price < avg_price * 0.6:
                score += 20

            CONDITION_KEYWORDS = ["como nueva", "perfecto estado", "muy buen estado", "impecable"]
            if price < avg_price * 0.7:
                if any(kw in text_lower for kw in CONDITION_KEYWORDS):
                    score += 20

    description = item.get("description", "")
    if description and len(description) < 50:
        score += 10

    if seller_items_count and seller_items_count > 3:
        score += 20

    images = item.get("images", [])
    if not images:
        score += 5

    return min(score, 100)


# --- ENRIQUECER ---

def enrich_items(items):
    prices = [
        item.get("price", {}).get("amount") for item in items
        if item.get("price", {}).get("amount")
    ]
    prices = [p for p in prices if p is not None and p > 0]

    seller_counts = {}
    for item in items:
        seller_id = item.get("user_id")
        if seller_id:
            seller_counts[seller_id] = seller_counts.get(seller_id, 0) + 1

    enriched_items = []

    for item in items:
        enriched = item.copy()

        # ----------------------------------------------------------------
        # 💡 CORRECCIÓN GEOSPATIAL: Crear el campo location.geopoint
        # ----------------------------------------------------------------
        location = item.get("location", {})
        lat = location.get("latitude")
        lon = location.get("longitude")
        
        # Si Wallapop nos da lat/lon, creamos el campo 'geopoint' anidado.
        if lat is not None and lon is not None:
            # Asegúrate de que el objeto 'location' exista en el documento enriched
            if "location" not in enriched:
                enriched["location"] = {}
                
            # Crea el campo 'geopoint' con la estructura requerida (lat, lon)
            enriched["location"]["geopoint"] = {
                "lat": lat,
                "lon": lon
            }
        # ----------------------------------------------------------------
        
        enriched["crawl_timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        price = item.get("price", {}).get("amount")
        enriched["relative_price_index"] = calculate_relative_price_index(price, prices)

        text = f"{item.get('title', '')} {item.get('description', '')}"

        found_keywords, found_categories = detect_suspicious_keywords(text)

        seller_id = item.get("user_id")
        seller_count = seller_counts.get(seller_id, 0)

        risk_score = calculate_risk_score(item, prices, seller_count, found_categories, text.lower())

        enriched["enrichment"] = {
            "suspicious_keywords": list(set(found_keywords)),
            "suspicious_keywords_count": len(set(found_keywords)),
            "risk_score": risk_score,
            "relative_price_index": enriched["relative_price_index"],
            "seller_items_today": seller_count,
            "description_length": len(item.get("description", "")),
            "has_images": len(item.get("images", [])) > 0,
            "image_count": len(item.get("images", [])),
        }

        enriched_items.append(enriched)

    return enriched_items


# --- ELASTICSEARCH ---

def send_to_elastic(items):
    if not items:
        return

    bulk_lines = []
    for item in items:
        action = {"index": {"_index": INDEX_NAME, "_id": item.get("id")}}
        bulk_lines.append(json.dumps(action, ensure_ascii=False))
        bulk_lines.append(json.dumps(item, ensure_ascii=False))

    payload = "\n".join(bulk_lines) + "\n"

    try:
        r = requests.post(
            f"{ES_URL}/_bulk",
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/x-ndjson"},
            timeout=10,
        )
        r.raise_for_status()
        print(f"✓ Enviados {len(items)} documentos a Elasticsearch (índice {INDEX_NAME})")
    except Exception as e:
        print(f"⚠️  Error enviando a Elasticsearch: {e}")


# --- MAIN ---

if __name__ == "__main__":

    print("=" * 70)
    print("📡 Obteniendo MOTOS (toda España, sin restricciones geográficas)")
    print("=" * 70 + "\n")

    daily_filename = get_daily_filename()
    existing_ids = load_existing_ids(daily_filename)
    print(f"Cargados {len(existing_ids)} IDs existentes para el día.\n")

    all_items = []

    search_queries = [
        ("moto", 14000),   # Categoría Motorbike
    ]

    for keywords, category_id in search_queries:
        print(f"🔍 Buscando: '{keywords}' (category_id={category_id})")
        items = fetch_all_pages(keywords, category_id)

        if items:
            print(f"   → Total adquiridos: {len(items)} items\n")
            all_items.extend(items)
        else:
            print("   ℹ No se encontraron items.\n")

    unique_items, dupes_internal = remove_duplicates(all_items)
    print(f"✓ Items únicos: {len(unique_items)} | Eliminados internos: {dupes_internal}\n")

    filtered_items, removed_clothing_count = filter_clothing_items(unique_items)
    print(f"✓ Ítems descartados (Indumentaria): {removed_clothing_count}")
    print(f"✓ Ítems para análisis: {len(filtered_items)}\n")

    new_items_to_save = [
        item for item in filtered_items if item.get("id") not in existing_ids
    ]
    duplicates_external = len(filtered_items) - len(new_items_to_save)
    print(f"✓ Ítems descartados (ya estaban en JSON): {duplicates_external}")
    print(f"✓ Ítems NUEVOS listos para enriquecer: {len(new_items_to_save)}\n")

    enriched_new_items = enrich_items(new_items_to_save)
    print(f"✓ {len(enriched_new_items)} items enriquecidos\n")

    if enriched_new_items:
        save_daily_file(enriched_new_items, daily_filename)
        print(f"✅ Archivo guardado: {daily_filename}")
        send_to_elastic(enriched_new_items)
    else:
        print("\n⚠️ No hay datos nuevos para guardar.")