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

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copia o código e o frontend compilado
COPY . .
COPY --from=frontend /app/dist ./dist

EXPOSE 3000

CMD python -m gunicorn wsgi:app --bind 0.0.0.0:${PORT:-3000} --workers 1 --timeout 60 --access-logfile - --error-logfile -
