# Imagem de produção da API + frontend estático (somente Python).
FROM python:3.13-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RG_AMBIENTE=producao \
    RG_FRONTEND_DIR=/app/frontend \
    RG_STORAGE_DIR=/data/storage

# Tesseract com idioma português (OCR principal) e bibliotecas do OpenCV usadas pelo RapidOCR (reserva).
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home /app rg \
 && mkdir -p /data/storage && chown -R rg /data

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
RUN rm -f backend/.env && chown -R rg /app

USER rg
WORKDIR /app/backend
EXPOSE 8000
VOLUME ["/data/storage"]

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/saude', timeout=4)"

# gthread é obrigatório para WebSockets (cada conexão ativa ocupa uma thread).
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--worker-class", "gthread", \
     "--workers", "2", "--threads", "64", "--timeout", "120", "--graceful-timeout", "30", \
     "--access-logfile", "-", "--forwarded-allow-ips", "*"]
