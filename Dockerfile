FROM python:3.11-slim

# Instalar cron
RUN apt-get update && apt-get install -y cron && rm -rf /var/lib/apt/lists/*

# Asegurar que python sea visible para cron
RUN ln -sf /usr/local/bin/python /usr/bin/python && \
    ln -sf /usr/local/bin/python3 /usr/bin/python3

# Copiar código
WORKDIR /app
COPY poller_wallapop.py .
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Crear cron job (usando ruta completa del script)
RUN echo "*/5 * * * * /usr/bin/python /app/poller_wallapop.py >> /var/log/cron.log 2>&1" \
    > /etc/cron.d/poller-cron && \
    chmod 0644 /etc/cron.d/poller-cron && \
    crontab /etc/cron.d/poller-cron

# Crear log
RUN touch /var/log/cron.log

# Ejecutar cron en primer plano
CMD ["cron", "-f"]
