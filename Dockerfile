FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for OCR (optional features)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        ghostscript \
    && rm -rf /var/lib/apt/lists/*

COPY LevitechDemo/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY LevitechDemo /app

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
