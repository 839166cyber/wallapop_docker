# wallapop_docker

Este proyecto implementa un **pipeline de monitorización y detección de anuncios sospechosos en Wallapop**, centrado en la categoría **Motocicletas**, como parte del **Assignment 2 del curso de Network Monitoring (NM)**.

El sistema simula una herramienta de análisis utilizada por equipos de investigación para detectar posibles fraudes, anuncios de riesgo o comportamientos anómalos en marketplaces online.

---

## 📌 Objetivo del proyecto

Diseñar e implementar un **pipeline completo de monitorización**, que:

* Obtenga anuncios recientes desde la **API pública de Wallapop**
* Filtre y normalice los datos
* Enriquezca los anuncios con métricas de riesgo
* Ingestione los datos en **Elasticsearch**
* Permita su análisis mediante **Kibana**
* Sirva como base para **alertas con Elastalert2**

---

## 🧱 Arquitectura del sistema

```
Wallapop API
     ↓
Python Poller (poller_wallapop.py)
     ↓
Filtrado + Enriquecimiento
     ↓
Elasticsearch (Bulk API)
     ↓
Kibana Dashboards / Elastalert2
```

El proyecto está preparado para ejecutarse mediante **Docker Compose**.

---

## 📂 Estructura del repositorio

```
.
├── poller_wallapop.py      # Script principal de adquisición y enriquecimiento
├── Dockerfile              # Imagen Docker para el poller
├── docker-compose.yml      # Stack con Elasticsearch y el poller
├── requirements.txt        # Dependencias Python
└── README.md               # Documentación del proyecto
```

---

## ⚙️ Funcionamiento del poller

El script `poller_wallapop.py`:

1. Consulta la API de Wallapop usando:

   * `category_id = 14000` (Motorbikes)
   * `time_filter = today`
   * Orden por anuncios más recientes
2. Descarta:

   * Anuncios duplicados
   * Artículos de indumentaria o accesorios
3. Enriquece cada anuncio con:

   * **Índice de precio relativo**
   * **Palabras clave sospechosas**
   * **Actividad del vendedor**
   * **Score de riesgo (0–100)**
4. Añade:

   * Timestamp de crawling
   * Campo `location.geopoint` compatible con Elasticsearch
5. Envía los documentos a Elasticsearch mediante la **Bulk API**

---

## 🚨 Lógica de riesgo implementada

El `risk_score` se calcula combinando señales como:

* Precio anormalmente bajo respecto a la media
* Palabras clave críticas:

  * `sin papeles`, `despiece`, `sin itv`, `urgente`, `chollo`, etc.
* Descripciones demasiado cortas
* Vendedores con múltiples anuncios en el mismo día
* Falta de imágenes

El score final está limitado a un máximo de **100**.

---

## 🐳 Despliegue con Docker

### Requisitos

* Docker
* Docker Compose

### Ejecución

```bash
docker compose up --build
```

Esto levanta:

* Elasticsearch
* El contenedor del poller, que envía los datos automáticamente al índice configurado

---

## 🔍 Elasticsearch

* **Índice:** `wallapop-motos`
* **Ingestión:** Bulk API
* **Campos destacados:**

  * `price.amount`
  * `location.geopoint`
  * `crawl_timestamp`
  * `enrichment.risk_score`
  * `enrichment.suspicious_keywords`

---

## 📊 Kibana

Con los datos indexados se pueden crear dashboards como:

* Distribución de precios
* Anuncios nuevos en el tiempo
* Top vendedores por volumen
* Mapa geográfico de anuncios
* Histogramas de `risk_score`
* Frecuencia de palabras sospechosas

Estos dashboards constituyen el **Fraud Radar** del proyecto.

---

## 🚨 Alertas (Elastalert2)

El proyecto está diseñado para soportar reglas como:

* Anuncios con `risk_score > 60`
* Precios extremadamente bajos
* Presencia de keywords críticas
* Vendedores con actividad anómala

*(La implementación concreta de Elastalert2 no la he realizado).*

---

## ⚠️ Consideraciones éticas

* No se interactúa con vendedores
* No se elude ningún mecanismo de protección
* Solo se usa información pública
* El sistema **no clasifica fraude**, solo **detecta señales de riesgo**
* Uso estrictamente académico

---

## 🎓 Contexto académico

Proyecto desarrollado como parte del:

**Assignment 2 – Hunting Scams on Wallapop**
Curso: *Network Monitoring*

El sistema replica el diseño de pipelines reales usados en entornos SOC/NOC para análisis de marketplaces.

---
