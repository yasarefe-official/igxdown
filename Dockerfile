# Daha spesifik ve güncel bir Python versiyonu kullanmak iyidir
FROM python:3.11-slim

# Ortam değişkenlerini ayarla
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Çalışma dizinini ayarla
WORKDIR /app

# Önce sadece requirements'ı kopyala ve kur. 
# Bu, kod değiştiğinde her seferinde paketlerin yeniden kurulmasını önler (Docker cache).
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Şimdi uygulamanın geri kalanını kopyala
COPY . .

# Koyeb portu otomatik olarak PORT değişkeniyle verir. 
# Dockerfile'da sabit bir değer vermek yerine bu değişkeni kullanalım.
# EXPOSE komutu aslında sadece bilgilendirme amaçlıdır, 
# ama yine de doğru portu göstermek iyi bir pratiktir.
# CMD'de ise bu değişkeni kullanmak zorunludur.
# PORT değişkeni Koyeb tarafından sağlanmazsa varsayılan olarak 8080 kullanır.
ENV PORT=${PORT:-8080}
EXPOSE ${PORT}

# Uygulamayı başlat. Portu sabit yazmak yerine Koyeb'den gelen PORT değişkenini kullan.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "$PORT"]
