# Kariyer Portalı — Öğrenci CV / Kurum Aday Havuzu Platformu

Öğrencilerin eğitim, deneyim, sertifika ve projelerini ayrı ayrı yönetebildiği,
transkript yükleyebildiği; kurumların ise filtreli bir aday havuzunda öğrenci
CV'lerini profesyonel bir formatta inceleyebildiği Flask tabanlı bir platform.

## Mimari

- **Backend:** Flask + Flask-SQLAlchemy + Flask-Login, SQLite veritabanı
- **Frontend:** Sunucu taraflı Jinja2 şablonları + Tailwind CSS (CDN) + FontAwesome
  ikonlar + hafif vanilla JavaScript (sekme geçişi, dinamik satır ekleme/silme,
  mobil menü)
- **Veri modeli:** `User` tablosu hem öğrenci hem kurum hesaplarını tutar
  (`role` alanı ile ayrılır). Öğrencinin eğitim/deneyim/sertifika/proje
  bilgileri **ayrı ilişkisel tablolarda** (`Education`, `Experience`,
  `Certificate`, `Project`) tutulur — her biri `User`'a `student_id` ile
  bağlıdır ve öğrenci silinirse otomatik silinir (cascade).

## Öne çıkan özellikler

**Öğrenci tarafı**
- Kayıt/giriş (şifreler hash'lenerek saklanır)
- Sekmeli CV formu: Genel Bilgiler, Eğitim, Deneyim, Sertifikalar, Projeler
- Her bölümde JavaScript ile "+ Satır Ekle" / satır silme (çöp kutusu ikonu)
- Transkript yükleme (PDF / JPG / PNG, azami 10 MB)
- Dashboard: profil doluluk yüzdesi (progress bar), eksik bölüm uyarıları,
  istatistik kartları, transkript durumu
- "Kurumlara Nasıl Görünüyorum?" önizleme sayfası (kurumların göreceği CV
  görünümünün birebir aynısı, salt-okunur)

**Kurum tarafı**
- Kayıt/giriş
- Aday Havuzu: sol filtre paneli (bölüme göre, isme göre arama, sadece
  transkripti olanlar), sağda kart (grid) düzeninde adaylar
- Aday detay sayfası: iki kolonlu profesyonel CV formatı — sol kolonda
  iletişim/özet/transkript butonu, sağ kolonda eğitim/deneyim/sertifika
  zaman çizelgesi (timeline) ve proje kartları

Bölüm listesi `models.py` içindeki `DEPARTMENTS` sabitinde tanımlı:
`Fiber Teknolojisi`, `Kurumsal İletişim`. Yeni bölüm eklemek için bu listeye
eklemek yeterli.

## Kurulum

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Uygulama `http://127.0.0.1:5000` adresinde çalışır. İlk çalıştırmada
`cv_platform.db` adında bir SQLite veritabanı otomatik oluşturulur.

> **Not:** Mevcut bir `cv_platform.db` dosyanız varsa (eski, düz-metin tabanlı
> sürümden kalma) yeni tablo yapısıyla uyumlu değildir. Geliştirme
> aşamasındaysanız dosyayı silip uygulamayı yeniden başlatmanız yeterli;
> gerçek verisi olan bir ortamda ise Alembic/Flask-Migrate ile migrasyon
> yazmanız gerekir.

## Profil doluluk yüzdesi nasıl hesaplanıyor?

`User.profile_completion()` şu ağırlıklarla hesaplar:
- Genel bilgiler + özet: %25
- En az 1 eğitim kaydı: %25
- Transkript yüklenmiş olması: %20
- En az 1 deneyim veya proje: %15
- En az 1 sertifika: %15

`%85` ve üzeri "profil eksiksiz" kabul edilir.

## Önemli notlar / prodüksiyona geçmeden önce yapılacaklar

- **Tailwind CDN:** Şu an hızlı geliştirme için Tailwind'in Play CDN sürümü
  (`cdn.tailwindcss.com`) kullanılıyor. Gerçek prodüksiyonda derleme
  adımlı (build) bir Tailwind kurulumuna (npm + `tailwindcss` CLI/PostCSS)
  geçmeniz performans ve önbellekleme açısından önerilir.
- **E-posta doğrulama yok:** Öğrenciler herhangi bir e-posta ile kayıt
  olabiliyor. Gerçek okul e-postası zorunluluğu istiyorsanız kayıt sırasında
  e-posta domainini kontrol edin (örn. yalnızca `@ogrenci.universite.edu.tr`
  ile bitenlere izin verin) veya doğrulama linki gönderen bir akış ekleyin.
- **SECRET_KEY:** Prod ortamında `SECRET_KEY` ortam değişkenini mutlaka
  güçlü, rastgele bir değerle ayarlayın.
- **Veritabanı:** Şu an SQLite kullanılıyor. Çok kullanıcılı gerçek üretim
  ortamı için PostgreSQL'e geçmek isteyebilirsiniz; `SQLALCHEMY_DATABASE_URI`
  satırını değiştirmek ve tabloları migrasyonla oluşturmak yeterli.
- **Dosya depolama:** Transkriptler sunucunun diskinde `uploads/transcripts/`
  altında tutulur. Bulut sunucuya taşırken bu klasörün kalıcı bir disk/volume
  üzerinde olduğundan emin olun; büyük ölçekte S3 benzeri bir nesne
  depolamaya geçmek daha sağlıklı olur.
- **Kurum onayı:** Şu an her kurum serbestçe kayıt olup tüm öğrencileri
  görebiliyor. İsterseniz kurum hesaplarını admin onayından geçirecek bir
  `is_approved` alanı eklenebilir.
