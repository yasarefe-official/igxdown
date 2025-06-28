FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

COPY requirements.txt .
RUN echo "Forcing re-installation of packages" && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# Koyeb bu PORT değişkenini otomatik olarak sağlar.
# Biz de onu uvicorn'a geçireceğiz.
# Lokal testler için varsayılan bir değer atamak iyi bir pratiktir.
ENV PORT=${PORT:-8080}
EXPOSE ${PORT}

# UYGULAMAYI BAŞLAT (SHELL FORM KULLANILARAK)
CMD uvicorn main:app --host 0.0.0.0 --port $PORT
