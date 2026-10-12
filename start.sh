#!/bin/sh
set -e

# Kariyer Portalı — kap başlangıç betiği
#
# DIKKAT: Bu dosyanın satır sonları LF olmalıdır (CRLF değil). Windows'ta
# CRLF ile kaydedilirse Linux "#!/bin/sh\r" diye okur ve kap
# "no such file or directory" hatasıyla açılmaz. .gitattributes bunu
# zorluyor; elle düzenlerken editörünüzün LF kullandığından emin olun.

DB="${DATA_DIR}/cv_platform.db"

mkdir -p "${DATA_DIR}/uploads/transcripts" "${DATA_DIR}/uploads/photos"

if [ ! -f "$DB" ]; then
    # --- İlk açılış: veritabanı henüz yok ---
    # Şema modellerden üretilir (create_all) ve bölümler eklenir.
    # Ardından migrasyonlar "uygulanmış" işaretlenir: tablolar zaten güncel
    # şemayla oluştuğu için upgrade çalıştırmak kolon eklemeye kalkar ve
    # "duplicate column" hatası verir.
    echo "[start] Veritabanı yok, sıfırdan oluşturuluyor: $DB"
    python -c "from app import create_app; create_app()"
    flask --app app db stamp head
else
    # --- Mevcut veritabanı: bekleyen migrasyonları uygula ---
    echo "[start] Mevcut veritabanı bulundu, migrasyonlar uygulanıyor"
    flask --app app db upgrade
fi

echo "[start] gunicorn başlatılıyor (port ${PORT})"

# --workers 2: SQLite tek dosyaya yazdığı için çok işçi eşzamanlı yazmada
#   kilitlenmeye yol açabilir. Bu ölçekte 2 yeterli ve güvenli.
# --timeout 60: PDF üretimi gibi yavaş istekler kesilmesin.
exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers 2 \
    --timeout 60 \
    --access-logfile - \
    --error-logfile - \
    app:app
