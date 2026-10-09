# Kariyer Portalı — Öğrenci CV / Kurum Aday Havuzu Platformu

Öğrencilerin eğitim, deneyim, sertifika ve projelerini ayrı ayrı yönetebildiği,
transkript yükleyebildiği; kurumların ise filtreli ve sıralanabilir bir aday
havuzunda öğrenci CV'lerini belge düzeninde inceleyebildiği Flask tabanlı bir
platform.

## Mimari

- **Backend:** Flask + Flask-SQLAlchemy + Flask-Login, SQLite veritabanı
- **Frontend:** Sunucu taraflı Jinja2 şablonları + **kendi CSS'i**
  (`static/style.css`, derleme adımı yok) + hafif vanilla JavaScript
  (sekme geçişi, dinamik satır ekleme/silme, mobil menü, kaydedilmemiş
  değişiklik koruması). **CSS çatısı veya ikon kütüphanesi kullanılmıyor.**
- **Veri modeli:** `User` tablosu hem öğrenci hem kurum hesaplarını tutar
  (`role` alanı ile ayrılır). Öğrencinin eğitim/deneyim/sertifika/proje
  bilgileri **ayrı ilişkisel tablolarda** (`Education`, `Experience`,
  `Certificate`, `Project`) tutulur — her biri `User`'a `student_id` ile
  bağlıdır ve öğrenci silinirse otomatik silinir (cascade).

Dışarıdan çekilen tek kaynak Google Fonts üzerinden IBM Plex ailesidir.

## Tasarım sistemi

Arayüzü değiştirecek biri için en önemli bölüm burasıdır.

### Hibrit dil

Ürünün iki tarafı farklı iş yapar, bu yüzden iki farklı görsel dil kullanır:

| Nerede | Dil | Nasıl |
|---|---|---|
| Açılış, giriş/kayıt, CV belgesi, öğrenci paneli | **Editoryal** | Serif başlıklar, kağıt yüzey, saç teli çizgiler, ferah ölçek |
| Kurum aday havuzu | **Yoğun araç** | Kompakt tablo satırları, mono tabular rakamlar, sıkı ölçek |

Kural: **kamuya dönük her şey editoryal, kurumun çalışma ekranı araçtır.**

### Token'lar

Tüm renk, tipografi ve boşluk değerleri `static/style.css` başındaki `:root`
bloğunda tanımlıdır. Siteyi baştan aşağı değiştirmek için **yalnızca bu bloğa
dokunmak yeterlidir**; hiçbir bileşen sabit renk veya boyut içermez.

```css
--accent: #174455;   /* derin petrol mavisi; ekranda en fazla 3 yerde */
--paper:  #faf9f6;   /* sıcak kağıt zemini */
--t-md:   15px;      /* genel gövde metni — tüm ölçek buna bağlı */
--r-2:    3px;       /* yarıçap tavanı; büyük yuvarlaklık yok */
```

### Tipografi

Tek süperfamilya (IBM Plex) üç register'da kullanılır:

- **Sans** → arayüz metni
- **Mono** → sayılar, kolon başlıkları, etiketler (`font-variant-numeric: tabular-nums`
  sayesinde rakamlar kolonda hizalanır)
- **Serif** → belge başlıkları, kayıt başlıkları, manşet rakamları

### Bilinçli tercihler

Aşağıdakiler unutulmuş değil, kasıtlıdır:

- **Gölge yerine çizgi.** Tek bir `--shadow` token'ı vardır, o da yalnızca
  yapışkan tablo başlığı ve kağıt yüzey için.
- **Dekoratif ikon yok.** Yalnızca işlevsel glifler (arama, açılır liste oku,
  hamburger) ve onlar da CSS içinde gömülü SVG.
- **Renkli pill rozet yok.** Bölüm, durum ve etiketler düz metin + ince çizgi
  ile gösterilir.
- **Vesikalıklar daire değil kare.** CV'deki fotoğraf gibi okunması için.

### Bileşen haritası

| Önek | Nerede kullanılır |
|---|---|
| `.doc*` | CV belgesi, öğrenci paneli, KVKK sayfası (kağıt yüzey) |
| `.entry*` | Belge içindeki kayıtlar (solda mono tarih rayı) |
| `.table`, `.sort`, `.meter` | Kurum aday havuzu tablosu |
| `.auth*` | Giriş/kayıt sayfaları (`auth_base.html` ile) |
| `.tabs`, `.formgrid`, `.rowitem` | CV formu |
| `.gauge`, `.stat*` | Öğrenci paneli göstergeleri |

Dinamik satırların numaraları (`01`, `02`…) **CSS sayacıyla** üretilir
(`.rowlist` / `.rowitem::before`). Satır eklenip silindiğinde numaralandırma
kendiliğinden düzelir; JavaScript saymaz.

## Öne çıkan özellikler

**Öğrenci tarafı**
- Kayıt/giriş (şifreler hash'lenerek saklanır)
- Sekmeli CV formu: Genel Bilgiler, Eğitim, Deneyim, Sertifikalar, Projeler
- Her bölümde "+ ... ekle" / "SİL" ile dinamik satır yönetimi
- Kaydedilmemiş değişiklikle sayfadan çıkarken tarayıcı uyarısı
- Transkript yükleme (PDF / JPG / PNG, azami 10 MB)
- Panel: profil doluluk yüzdesi, eksik bölüm listesi, içerik sayaçları,
  transkript durumu
- "Önizleme" sayfası — kurumların göreceği CV'nin birebir aynısı, salt-okunur

**Kurum tarafı**
- Kayıt/giriş (**hesap onaydan geçmeden giriş yapılamaz**, aşağıya bakın)
- Aday Havuzu: üstte filtre çubuğu (isim/e-posta/yetkinlik araması, bölüm,
  profil doluluğu, transkript durumu), altta **sıralanabilir tablo**
- 9 kolonda sıralama; sayfa başına 25 aday
- Dar ekranda tablo bloklara dönüşür ve ayrı bir sıralama seçicisi belirir
- Aday detayı: tek sayfalık CV belgesi, yazdırmaya hazır

**Ortak**
- Tasarımlı 403 / 404 / 413 / 500 sayfaları
- `/kvkk` — hangi verilerin tutulduğu ve kimin gördüğü (**metin tamamlanmamış**)
- Klavye erişimi: "içeriğe atla" linki, sekmelerde ok tuşu gezinmesi
- CV belgesi için yazdırma stili

Bölümler `Department` tablosunda tutulur. İlk açılışta `app.py` içindeki
`seed_departments()` fonksiyonu `Fiber Teknolojisi` ve `Kurumsal Bilişim`
kayıtlarını ekler. Yeni bölüm için bu listeye eklemek ya da doğrudan tabloya
kayıt girmek yeterlidir.

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate           # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Uygulama `http://127.0.0.1:5000` adresinde çalışır. İlk çalıştırmada
`cv_platform.db` otomatik oluşturulur.

### Kurum hesabı nasıl açılır (atlanırsa takılırsınız)

Kurum hesapları **onay bekler**; onaylanmadan giriş yapılamaz. Arayüzden kayıt
olduktan sonra ayrı bir terminalde:

```bash
venv\Scripts\flask --app app approve-company
```

Komut onay bekleyen kurumları listeler; ID girilir veya `all` yazılır.

> **Not:** Eski bir `cv_platform.db` dosyanız varsa yeni tablo yapısıyla uyumlu
> olmayabilir. Geliştirme aşamasında dosyayı silip yeniden başlatmak yeterli;
> gerçek verisi olan bir ortamda Flask-Migrate ile migrasyon yazılmalıdır.

## Profil doluluk yüzdesi nasıl hesaplanıyor?

`User.profile_completion()` şu ağırlıklarla hesaplar:

| Koşul | Puan |
|---|---|
| Ad, bölüm, telefon ve özetin tamamı dolu | 25 |
| En az 1 eğitim kaydı | 25 |
| Transkript yüklenmiş | 20 |
| En az 1 deneyim **veya** proje | 15 |
| En az 1 sertifika | 15 |

`%85` ve üzeri "profil eksiksiz" kabul edilir.

## Bilinen sorunlar

- **PDF indirme çalışmıyor.** `requirements.txt` reportlab sürümünü
  sabitlemiyor; gelen yeni sürüm (4.5+) xhtml2pdf 0.2.16 ile Windows'ta
  çakışıyor ve `PermissionError` veriyor (font geçici dosyadan okunamıyor).
  Çözüm için ya reportlab çalışan bir sürüme sabitlenmeli ya da PDF route'una
  `link_callback` eklenip font doğrudan diskten okutulmalı. Geçici çözüm:
  CV sayfasından tarayıcıyla yazdırmak (yazdırma stili hazır).
- **Bozuk bölüm verisi.** Eski bir şablon hatası yüzünden bazı kayıtların
  `department` alanına `<Department Kurumsal Bilişim>` gibi nesne metni
  yazılmış olabilir. Şablon düzeltildi, ancak **mevcut hatalı kayıtlar
  veritabanında duruyor** ve bu öğrenciler bölüm filtresinde çıkmaz.
  Bir `UPDATE` ile temizlenmeleri gerekir.
- **`updated_at` alanı yok.** Aday havuzundaki "KAYIT" kolonu hesabın açılış
  tarihini gösterir, CV'nin son güncellenme tarihini değil. Kurum için asıl
  değerli olan ikincisidir; modele bir alan eklenmesi gerekir.

## Prodüksiyona geçmeden önce

- **SECRET_KEY:** Ortam değişkenini mutlaka güçlü, rastgele bir değerle ayarlayın.
  Varsayılan değer yalnızca geliştirme içindir.
- **KVKK metni:** `/kvkk` sayfası tamamlanmamıştır. Veri sorumlusu, işleme
  amacı, saklama süresi ve başvuru yolu kurumun ilgili birimi tarafından
  yazılıp eklenmelidir. Footer'daki iletişim bilgileri de yer tutucudur.
- **E-posta doğrulama yok:** Öğrenciler herhangi bir e-posta ile kayıt
  olabiliyor. Okul e-postası zorunluluğu için kayıt sırasında domain kontrolü
  ekleyin veya doğrulama linki gönderen bir akış kurun.
- **Veritabanı:** SQLite kullanılıyor. Çok kullanıcılı üretim için PostgreSQL'e
  geçmek üzere `SQLALCHEMY_DATABASE_URI` değiştirilmeli ve tablolar migrasyonla
  oluşturulmalıdır.
- **Dosya depolama:** Transkriptler `uploads/transcripts/` altında diskte tutulur.
  Bulut sunucuda bu klasör kalıcı bir disk üzerinde olmalı; büyük ölçekte S3
  benzeri nesne depolamaya geçilmelidir.
- **Yetkilendirme:** Onaylı her kurum **tüm** öğrencileri ve transkriptlerini
  görebiliyor. Daha dar bir erişim modeli (ör. ilan bazlı başvuru) gerekiyorsa
  bu tasarım gözden geçirilmelidir.
