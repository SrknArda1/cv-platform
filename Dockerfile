# Kariyer Portalı — Fly.io dağıtım imajı
#
# Geliştirme sunucusu (app.run) yerine gunicorn kullanılır: Flask'ın kendi
# sunucusu tek istekle meşgul olur ve üretim için tasarlanmamıştır.

FROM python:3.12-slim

# Python'un kap içindeki davranışı:
#   PYTHONDONTWRITEBYTECODE — .pyc dosyası üretme, imaj şişmesin
#   PYTHONUNBUFFERED        — logları anında yaz, Fly loglarında gecikme olmasın
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Önce yalnızca requirements kopyalanır: kod değiştiğinde bu katman
# önbellekten gelir ve paketler yeniden indirilmez.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Veritabanı ve yüklenen dosyalar kalıcı diskte (fly.toml'daki volume) durur.
# Kabın kendi dosya sistemi her yeniden başlatmada sıfırlanır.
ENV DATA_DIR=/data \
    FLASK_DEBUG=0 \
    PORT=8080

EXPOSE 8080

# start.sh: önce şemayı hazırlar (migrasyon), sonra sunucuyu başlatır.
COPY start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
