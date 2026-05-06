# Stage 1: build do frontend React
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: servidor Python
FROM python:3.10-slim
# cache-bust: 2026-05-06

WORKDIR /app

# Dependências do sistema (curl necessário para HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código e o frontend compilado
COPY . .
COPY --from=frontend /app/dist ./dist

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD python -m gunicorn wsgi:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 2 \
    --worker-class sync \
    --timeout 60 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --access-logfile - \
    --error-logfile -
