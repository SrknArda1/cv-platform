# Devir notu

**Son güncelleme:** 2026-11-02 · **Sürüm:** v1.1.0 · **Dal:** `main`, çalışma kopyası temiz

Bu belge, projeyi devralan kişinin (veya aradan zaman geçtikten sonra kendinin)
5 dakikada bağlamı kurması içindir. Mimari ve tasarım kararları için
[README.md](README.md), dağıtım için [DAGITIM.md](DAGITIM.md).

---

## Durum

Kariyer Portalı: öğrenci–kurum eşleştirme platformu. Flask 3.0.3 + SQLite,
PythonAnywhere ücretsiz katmanda canlı.

| | |
|---|---|
| Canlı adres | https://srknarda1.pythonanywhere.com |
| API | https://srknarda1.pythonanywhere.com/api |
| Kod | `app.py` 1.647 satır · `api.py` 547 · `models.py` 280 · `style.css` 1.993 |
| Rotalar | 34 HTML + 7 JSON |
| Tablolar | 7 · Göçler: 7 |
| Gerçek veri | 25 öğrenci, 2 kurum, 22 sertifika |

Canlı veri durumu (2026-11-02): 10 öğrencinin transkripti var ama **hiçbiri
doğrulanmamış**; 22 sertifikanın **hiçbiri doğrulanabilir değil** (alanlar yeni,
kimse doldurmadı); 25 öğrencinin **11'i** profilini hiç doldurmamış. Bunlar hata
değil, veri girişi eksikliği.

---

## Bu oturumda yapılanlar

### 1. Sertifikalara dijital doğrulama (`87a3b22`)

`Certificate` modeline `credential_id` ve `credential_url` eklendi; CV sayfasında
"doğrula ↗" bağlantısı, PDF'te metin olarak basılıyor. Göç: `c4a1e07b92d5`.

Bunu ararken **gerçek bir güvenlik açığı** bulundu ve kapatıldı: öğrencinin
girdiği proje bağlantısı `href`'e denetlenmeden yazılıyordu. Jinja özel
karakterleri kaçırır ama **şemayı denetlemez** — `javascript:...` yazan bir
öğrencinin bağlantısına tıklayan kurum o kodu kendi oturumunda çalıştırırdı
(depolanmış XSS). Çözüm: `guvenli_baglanti()` ([app.py:243](app.py#L243)),
yalnızca `http`/`https` geçirir, şemasız adrese `https://` ekler.

### 2. PDF boşlukları sıkıştırıldı (aynı commit)

xhtml2pdf blok ögelere kenar boşluğu veriyordu; satır araları ölçüldü
(35,8 pt → 20,8 pt). Tek bölüme değil **tüm belgeye** uygulandı, tutarlılık
bozulmasın diye.

### 3. REST API katmanı (`871d51a`)

`api.py` içinde Blueprint olarak `/api/v1`. Mevcut HTML sayfalarına
dokunulmadı. 7 uç nokta, `data`/`meta`/`links` sözleşmesi, `selectinload` ile
N+1 çözümü, `hmac.compare_digest` ile API anahtarı denetimi.

### 4. Excel uyumlu CSV (`f6f5bd6`)

`?format=csv` üç uç noktada. UTF-8 BOM (Excel Türkçe'yi bozmasın) ve noktalı
virgül ayırıcı (Türkçe Excel'in liste ayırıcısı); `?delimiter=comma` ile
standart CSV.

### 5. API belge sayfası (`6905d79`)

`/api` — uç nokta listesi, JSON bağlantıları, CSV indirme düğmeleri, filtre
tablosu, Excel/pandas örnekleri. Swagger/Redoc'un elle yazılmış karşılığı.

---

## Alınan kararlar ve gerekçeleri

Bunlar sorgulanabilir kararlardır; değiştirmeden önce gerekçesini okuyun.

**API kişisel veri döndürmez.** Ad, e-posta, telefon, transkript API'de yok.
Serileştirme katmanı ([api.py:241](api.py#L241)) modeli değil, açıkça seçilen
alanları döner — modele yeni kolon eklendiğinde kendiliğinden sızmasın diye.
Veritabanında 25 gerçek öğrencinin verisi var ve API girişsiz açık.

**Yalnızca `GET`.** Dış sistemin yazması gerekmiyor; salt-okunur API saldırı
yüzeyini küçültür.

**Sürümleme ilk günden (`/v1`).** Sonradan eklenemez: o noktada sürümsüz
çalışan istemciler olur.

**İngilizce JSON anahtarları.** Türkçe anahtarlar pandas/Excel tarafında
kodlama sorunu çıkarır.

**Framework değiştirilmedi.** Ders materyali Laravel; proje Flask olarak
verildi ve hoca "ne ile başladıysanız onunla devam edin" dedi. Kavram
eşlemesi README ve [rehber belgede](https://claude.ai/artifact/N9ZiF4WSusseXx1WgSTAoB)
yazılı. Ayrıca PythonAnywhere PHP çalıştırmaz.

**API anahtarı ortam değişkeninde.** `API_ANAHTARI` WSGI dosyasında tanımlı.
Tanımsızsa `/api/v1/ozet/detay` **503** döner — sessizce korumasız kalmaz.

---

## ⚠️ Bilerek düzeltilmemiş olanlar

Bunları kendiliğinizden düzeltmeyin; sahibine sorun.

**Bozuk bölüm verisi.** Bir öğrencinin `department` alanında `<Department ...>`
nesne metni var. Şablon hatası düzeltildi, **kayıt düzeltilmedi** — hocaya
"bulduğum sorun" olarak sunulmak üzere bırakıldı.

> Not: hafızadaki "PDF indirme bozuk" maddesi **artık geçersiz**. PDF bu
> oturumda tamamen yeniden yazıldı ve çalışıyor (fontlar `pdfmetrics` ile
> kaydediliyor, `@font-face` kullanılmıyor).

---

## Yarım kalan işler

### 1. Şifre sıfırlama yok

Şifresini unutan kullanıcının hiçbir çaresi yok. E-posta/SMS **yapılamaz**:
ücretsiz katman dışarı SMTP'ye izin vermiyor. Yapılabilir olan: yönetici
panelinden geçici şifre üretme (~45 dk).

### 2. Telefon görünürlüğü — önce sorulacak

Kurumlar öğrencinin telefonunu CV sayfasında ve PDF'te görüyor. Hocanın
"kurumlar numarayı görmemeli, okul üzerinden iletişim kurulmalı" dediği
düşünülüyor ama **teyit edilmedi**. Netleşince gizlemek 10 dakika.
Tahminle hareket etmeyin.

### 3. Ev temizliği

- `git worktree remove ../cv-platform-orijinal --force` — içinde gerçek
  veritabanının, bir transkriptin ve 3 fotoğrafın kopyaları var
- Mükerrer aday: "Kaan Yaşar Kaya" iki hesapla kayıtlı
- Yalnızca 2 bölüm tanımlı (Fiber Teknolojisi, Kurumsal Bilişim); 25 öğrencinin
  11'i tanımlı bölümlerin dışında. Hangi bölümlerin ekleneceği hocaya sorulacak

---

## Testler

`pytest` ile **147 test** (`tests/`). Gerçek veritabanına dokunmazlar;
`DATA_DIR` geçici klasöre yönlendirilir.

```bash
pip install -r requirements-dev.txt
pytest
```

Mesajlaşma ve kurum onay/ret akışı `tests/test_akis.py` ile uçtan uca sınanıyor.
Kapsanmayan: dosya yükleme (transkript/fotoğraf).

## Bilinen teknik borç

| Eksik | Neden sorun | Çözüm |
|---|---|---|
| `app.py` 1.647 satır | Tek dosyada 34 rota | Blueprint'lere bölmek — API ile başlandı |
| Sıralama Python'da | GPA ilişkili tabloda **metin**; SQL'de `ORDER BY` yapılamıyor | GPA'yı `User` üzerinde sayısal kolona taşımak |
| Bölüm metin olarak | Yabancı anahtar yok; ad değişirse kayıtlar güncellenmez | `department_id` yabancı anahtarı (bir göç işi) |
| Uygulama logu yok | Hata sonrası iz sürülemiyor | `logging` ile dosyaya yazmak |
| KVKK metni eksik | Hukuki eksik | Kurumun ilgili birimi yazmalı |
| SQLite tek yazar | Yüksek eşzamanlı yazımda kilit | PostgreSQL; ORM kullanıldığı için kod değişmez |

**Ölçülmüş rakam (2026-11-05):** 2.000 öğrencide aday havuzu ve yönetici sayfaları
**6.000 sorgudan 21'e**, ~2.500 ms'den 130-240 ms'ye indi. Çözüm her yerde aynı:
`ogrenci_sorgusu()` ile `selectinload`. Bedeli: 2.000 öğrencide varsayılan
aday havuzu 66 ms'den 150 ms'ye çıkıyor (25 ve 200 öğrencide yine de daha hızlı).
Sorguya hâlâ yabancı anahtar indeksi eklenebilir; göç gerektirdiği için yapılmadı.
Fonksiyon: [api.py:265](api.py#L265).

---

## Sıradaki adımlar

Öncelik sırasıyla:

1. **PythonAnywhere'de günlük yedek görevi kur** (`flask yedekle`, komut README
   "Araçlar" bölümünde). Komut hazır ama sunucuda zamanlanmadıkça yedek alınmıyor.
2. **Telefon görünürlüğünü hocaya sor**, cevaba göre uygula.
3. **Worktree'yi sil** — gerçek kişisel veri kopyaları diskte duruyor.
4. **Şifre sıfırlama** (yönetici eliyle).
5. **Bölüm listesini netleştir** ve `department_id` göçünü planla.
6. **Testleri genişlet** — dosya yükleme (transkript/fotoğraf) henüz kapsanmıyor.

---

## Çalışmaya başlamadan bilinmesi gerekenler

**Venv zorunlu.** `python app.py` doğrudan çalışmaz; sistem Python'unda paketler
yok. Her yeni terminalde:

```powershell
.\venv\Scripts\Activate.ps1
```

**Göç varsa sunucuda `export DATA_DIR` şart.** Atlanırsa `flask db upgrade`
gerçek veritabanını değil, `~/cv-platform/` içinde **yeni boş bir veritabanı**
oluşturup onu yükseltir; çıktı başarılı görünür ama asıl veritabanı eski
sürümde kalır ve site çöker. Kontrol: `ls ~/cv-platform/*.db` hiçbir şey
döndürmemeli.

**Dağıtım sırası:** yerel test → `git push` → sunucuda `git pull` →
(şema değiştiyse) `flask db upgrade` → Web sekmesinden **Reload**.

**Gerçek veriyle çalışıyorsunuz.** Yerel `cv_platform.db` içinde gerçek
e-posta adresleri var (`.gitignore`'da, git'e gitmiyor). Test yazarken
`DATA_DIR` ortam değişkeniyle ayrı bir klasör kullanın; bu oturumdaki tüm
testler öyle çalıştı ve gerçek veriye hiç dokunulmadı.

**PythonAnywhere ücretsiz katman:** 3 ayda bir Web sekmesinden
"Run until 3 months from today" düğmesine basılmalı, yoksa site durur.
