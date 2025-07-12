# 1. Temel imaj olarak Python'un slim (hafif) bir sürümünü kullan
FROM python:3.11-slim

# Ortam değişkenleri
# - PYTHONDONTWRITEBYTECODE: .pyc dosyaları oluşturulmasını engeller
# - PYTHONUNBUFFERED: Logların doğrudan konsola yazılmasını sağlar (Render logları için iyi)
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# 2. Sistem paketlerini kur
# - apt-get update: Paket listesini günceller
# - apt-get install -y --no-install-recommends: Sadece gerekli paketleri kurar
#   - ffmpeg: yt-dlp'nin video ve sesi birleştirmesi için gerekli
#   - curl: Genel ağ işlemleri veya testler için faydalı olabilir (isteğe bağlı)
# - apt-get clean && rm -rf /var/lib/apt/lists/*: İmaj boyutunu küçültmek için gereksiz dosyaları temizler
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 3. Uygulama için çalışma dizini oluştur
WORKDIR /app

# 4. Bağımlılıkları kur
# - Önce sadece requirements.txt dosyasını kopyala. Bu, Docker'ın katman önbellekleme (layer caching)
#   özelliğinden faydalanarak, requirements.txt değişmediği sürece bu adımı tekrar çalıştırmasını engeller.
#   Bu, build sürelerini önemli ölçüde hızlandırır.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 5. Uygulama kodunu kopyala
# - requirements.txt'den sonra tüm proje dosyalarını kopyala. Bu, kodda her değişiklik
#   yaptığınızda sadece bu katmanın yeniden oluşturulmasını sağlar.
COPY . .

# 6. Uygulamayı çalıştır
# - Render bu komutu, container'ı (uygulama ortamını) başlatmak için kullanacak.
CMD ["python", "bot.py"]
