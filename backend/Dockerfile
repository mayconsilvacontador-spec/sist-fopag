# Backend SIST para DESENVOLVIMENTO.
# Roda o Django em Linux dentro do Docker: no Windows com Smart App Control ativo,
# as DLLs dos drivers PostgreSQL (psycopg / psycopg2) são bloqueadas.
# O código é montado como volume (ver docker-compose.yml) — alterações recarregam sozinhas.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# OCR local e gratuito (leitura de documentos digitalizados sem enviar nada para fora): Tesseract + português
RUN apt-get update     && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-por     && rm -rf /var/lib/apt/lists/*
ENV TESSDATA_PREFIX=/usr/share/tesseract-ocr/5/tessdata

COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
