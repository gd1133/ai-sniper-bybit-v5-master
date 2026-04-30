# Stage 1: build do frontend React
FROM node:20-slim AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: servidor Python
FROM python:3.10-slim
# cache-bust: 2026-04-28

WORKDIR /app

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código e o frontend compilado
COPY . .
COPY --from=frontend /app/dist ./dist

EXPOSE 8080

CMD python -m gunicorn wsgi:app --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120
