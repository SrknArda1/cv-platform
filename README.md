# Kariyer Portalı — Öğrenci CV / Kurum Aday Havuzu Platformu

Öğrencilerin eğitim, deneyim, sertifika ve projelerini ayrı ayrı yönetebildiği,
transkript yükleyebildiği; kurumların ise filtreli ve sıralanabilir bir aday
havuzunda öğrenci CV'lerini belge düzeninde inceleyebildiği Flask tabanlı bir
platform.

## Mimari

- **Backend:** Flask + Flask-SQLAlchemy + Flask-Login + Flask-Migrate +
  Flask-WTF (CSRF), SQLite veritabanı
- **Frontend:** Sunucu taraflı Jinja2 şablonları + **kendi CSS'i**
  (`static/style.css`, derleme adımı yok) + hafif vanilla JavaScript
  (sekme geçişi, dinamik satır ekleme/silme, mobil menü, kaydedilmemiş
  değişiklik koruması). **CSS çatısı veya ikon kütüphanesi kullanılmıyor.**
- **Veri modeli:** `User` tablosu öğrenci, kurum ve yönetici hesaplarını
  birlikte tutar (`role` alanı ile ayrılır: `student` / `company` / `admin`). Öğrencinin eğitim/deneyim/sertifika/proje
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
- **Sertifika dijital doğrulaması:** her sertifikaya belge/doğrulama numarası
  ve doğrulama bağlantısı eklenebilir. Kurum, CV'deki "doğrula" bağlantısıyla
  sertifikayı kaynağından (Credly, Coursera, BTK Akademi…) teyit eder; PDF
  çıktısında adres metin olarak basılır, kâğıda basılan CV'de de okunur
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

**Yönetici (kampüs koordinatörü)**
- Kurum onay ekranı: bekleyenler ve onaylılar ayrı tablolarda, tek tıkla
  onaylama ve erişim kaldırma
- Onay kaydı: her onaylı kurumda **kimin, ne zaman** onayladığı görünür
- Bölüm yönetimi: bölüm ekleme/silme. Öğrencisi olan bölüm silinemez
  (bölüm öğrenci kaydında metin olarak tutulduğu için silinirse o
  öğrenciler filtrelerde kaybolurdu)
- Yönetici hesabı **tarayıcıdan açılamaz**, yalnızca komutla oluşturulur

**Güvenlik**
- Şifreler hash'lenerek saklanır (Werkzeug / scrypt)
- Roller ayrı: öğrenci, kurum ve yönetici birbirinin sayfalarına giremez (403)
- Kurum hesapları onaydan geçmeden giriş yapamaz
- Yüklenen fotoğraf ve transkriptler giriş gerektirir
- **Öğrencinin girdiği adresler yalnızca `http`/`https` olabilir**
  (`guvenli_baglanti()`). Jinja özel karakterleri kaçırır ama şemayı
  denetlemez: `javascript:...` yazan bir öğrencinin bağlantısına tıklayan
  kurum o kodu kendi oturumunda çalıştırırdı. Şemasız yazılan adreslere
  (`credly.com/...`) reddetmek yerine `https://` eklenir
- Durum değiştiren her işlem POST ve **CSRF token** ile korunur
- **Giriş denemesi sınırı:** yönetici 5/dakika, öğrenci ve kurum 10/dakika.
  Sınırsız deneme olsaydı bir betik dakikada binlerce şifre deneyebilirdi —
  adresin tahmin edilebilir olması (`/admin/giris`) bu yüzden tek başına
  risk değil, asıl engel budur
- Oturum çerezi: `HttpOnly`, `SameSite=Lax`, dışa açık çalıştırmada `Secure`;
  oturum ömrü 31 gün değil **8 saat**
- Başarısız giriş denemeleri e-posta ve IP ile loglanır (sunucu çıktısında)
- Dışa açık çalıştırmada (`FLASK_DEBUG=0`) `SECRET_KEY` verilmemişse uygulama
  başlamayı reddeder
- Gerçek veritabanı ve yüklenen dosyalar ne git'e ne de sunucuya gider
  (`.gitignore` + `.dockerignore`)

**Ortak**
- Tasarımlı 400 / 403 / 404 / 413 / 500 sayfaları
- `/kvkk` — hangi verilerin tutulduğu ve kimin gördüğü (**metin tamamlanmamış**)
- Klavye erişimi: "içeriğe atla" linki, sekmelerde ok tuşu gezinmesi
- CV belgesi için yazdırma stili

Bölümler `Department` tablosunda tutulur. İlk açılışta `seed_departments()`
`Fiber Teknolojisi` ve `Kurumsal Bilişim` kayıtlarını ekler; sonrasında
yönetici `/admin/bolumler` ekranından ekleyip silebilir (kod değişikliği
gerekmez).

## API (`/api/v1`)

Dış sistemlerin veriyi program olarak okuyabilmesi için REST API katmanı.
Ayrı dosyada (`api.py`) bir **Blueprint** olarak durur; mevcut HTML
sayfalarına hiç dokunmaz. Sayfalar insana, API makineye konuşur.

| Uç nokta | Döndürdüğü |
| --- | --- |
| `GET /api/v1/` | API'nin kendini tanıtması: adres listesi ve filtreler |
| `GET /api/v1/ozet` | Öğrenci / kurum / sertifika sayımları |
| `GET /api/v1/ogrenciler` | Anonim öğrenci kayıtları, sayfalanmış |
| `GET /api/v1/ogrenciler/<id>` | Tek kayıt |
| `GET /api/v1/bolumler` | Bölüm bazında dağılım |
| `GET /api/v1/yetkinlikler` | Yetkinlik frekansı |
| `GET /api/v1/ozet/detay` | Ayrıntılı metrikler — **`X-API-Key` gerekir** |

`/api/v1/ogrenciler` filtreleri: `page`, `page_size`, `department`, `skill`,
`has_transcript`, `verified`, `min_completion`.

### Tasarım kararları

- **Sürümleme ilk günden** (`/api/v1`). Sonradan eklenemez: o noktada
  sürümsüz çalışan istemciler olur ve hepsi kırılır.
- **Yalnızca `GET`.** Dış sistemin veritabanına yazması gerekmiyor;
  salt-okunur API saldırı yüzeyini küçültür.
- **Kişisel veri dönmez.** Ad, e-posta, telefon ve transkript API'de
  **yoktur**. Serileştirme katmanı modeli değil, açıkça seçilen alanları
  döner — modele yarın yeni bir kolon eklendiğinde yanlışlıkla dışarı
  sızmasın diye. Açık bir uç nokta, sitenin tüm giriş korumasını baypas
  ederdi.
- **İngilizce anahtar adları.** Türkçe anahtarlar pandas ve Excel tarafında
  kodlama sorunu çıkarır.
- **Tutarlı sözleşme:** her yanıt `data` / `meta` / `links` iskeletinde;
  hata da aynı biçimde, böylece istemci tek ayrıştırıcı yazar.
- **`/api/` altında asla HTML.** `_error_page()` yolun `/api/` ile başlayıp
  başlamadığına bakar; API'de HTML hata sayfası dönseydi istemcinin
  ayrıştırıcısı çökerdi.
- **`selectinload`** ile ilişkiler tek seferde yüklenir. Olmasaydı her
  öğrenci için ayrı sorgu çalışırdı (N+1): 50 öğrenciye 201 sorgu yerine 5.
- **Hız sınırı** 120/dk, 2000/saat. Aşımda 429.
- **CORS** `*` — veri anonim ve salt-okunur olduğu için güvenli.

### API anahtarı

`/api/v1/ozet/detay` uç noktası `API_ANAHTARI` ortam değişkenini kullanır.
Tanımlı değilse uç nokta **503** döner — sessizce açık kalmaz. Anahtar
karşılaştırması `hmac.compare_digest` ile yapılır: sıradan `==` ilk farklı
karakterde erken çıkar ve yanıt süresi ölçülerek anahtar karakter karakter
bulunabilirdi (zamanlama saldırısı).

```bash
export API_ANAHTARI="uzun-rastgele-bir-dize"
curl -H "X-API-Key: uzun-rastgele-bir-dize" https://SUNUCU/api/v1/ozet/detay
```

## Dağıtım

Sunucuya kurulum adımları ayrı bir dosyada: **[DAGITIM.md](DAGITIM.md)**
(PythonAnywhere ve Fly.io için adım adım, ve gerçek kişisel verinin neden
sunucuya hiç gitmediği).

## Kurulum

```bash
python -m venv venv
venv\Scripts\activate           # Linux/macOS: source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Uygulama `http://127.0.0.1:5000` adresinde çalışır. İlk çalıştırmada
`cv_platform.db` otomatik oluşturulur.

### Veritabanı şeması güncelleme (migrasyon)

Şema değişiklikleri Flask-Migrate ile yönetilir. Mevcut bir veritabanını
güncel şemaya getirmek için:

```bash
venv/Scripts/flask --app app db upgrade
```

Modeli değiştirdikten sonra yeni migrasyon üretmek için:

```bash
venv/Scripts/flask --app app db migrate -m "ne degistigini anlatan mesaj"
venv/Scripts/flask --app app db upgrade
```

> Üretilen dosyayı **çalıştırmadan önce okuyun**. Alembic'in otomatik ürettiği
> kod her zaman doğru olmuyor; örneğin ilk migrasyonda `downgrade()` isimsiz
> bir yabancı anahtar kısıtı düşürmeye çalışıyordu ve o haliyle çalışmazdı.

> Sıfırdan oluşturulan veritabanlarında şema `db.create_all()` ile gelir;
> böyle bir veritabanını `flask --app app db stamp head` ile güncel
> işaretleyin, yoksa `upgrade` var olan kolonları eklemeye çalışır.

### Yönetici hesabı nasıl açılır

Yönetici hesabı tarayıcıdan açılamaz — kayıt sayfası yoktur. Olsaydı isteyen
herkes yönetici olup bütün öğrenci transkriptlerine erişebilirdi.

```bash
venv/Scripts/flask --app app create-admin
```

E-posta, ad ve şifre sorar. Giriş: `/admin/giris`

### Kurum hesabı nasıl açılır (atlanırsa takılırsınız)

Kurum hesapları **onay bekler**; onaylanmadan giriş yapılamaz. Arayüzden kayıt
olduktan sonra ayrı bir terminalde:

```bash
venv\Scripts\flask --app app approve-company
```

Komut onay bekleyen kurumları listeler; ID girilir veya `all` yazılır.
Aynı işi yönetici arayüzünden de yapabilirsiniz: `/admin/kurumlar`.

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

## Geliştirirken dikkat

**Yeni bir POST formu eklerken CSRF token'ını unutmayın:**

```html
<form method="POST" action="...">
  <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
  ...
</form>
```

Token olmadan form 400 ile reddedilir. GET formları (örn. aday havuzu filtresi)
token gerektirmez.

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
- **Depoda otomatik test yok.** Geliştirme sırasında kapsamlı testler
  yazılıp çalıştırıldı (CSRF, yönetici onay akışı, sıralama/filtreleme,
  form kaydetme) ancak bunlar projeye eklenmedi. Yeni gelen bir geliştirici
  "bu kod çalışıyor mu" sorusunu kodla cevaplayamaz.
- **Uygulama logu yok.** Kimin ne zaman giriş yaptığı, hangi kurumun hangi
  CV'yi görüntülediği kayıt altına alınmıyor. Kişisel veri işleyen bir
  sistemde erişim kaydı tutmak beklenir.
- **`app.py` 900+ satır.** Route'lar, hata sayfaları, yönetici işlemleri ve
  CLI komutları tek dosyada. Flask blueprint'leri ile bölünmesi gerekir.
- **Onay kaydı geçmiş tutmaz.** `approved_at` / `approved_by` yalnızca
  **mevcut** onayı tarif eder; erişim kaldırılınca temizlenir. Her onay ve
  iptal hareketinin geçmişi isteniyorsa ayrı bir kayıt tablosu gerekir.
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
