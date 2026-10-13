# Dağıtım

Uygulama platformdan bağımsız yazıldı. Platforma özel olan yalnızca üç şey var:

| Ayar | Ne işe yarar |
|---|---|
| `SECRET_KEY` | Oturum çerezlerini imzalar. **Zorunlu.** `FLASK_DEBUG=0` iken verilmezse uygulama başlamayı reddeder |
| `FLASK_DEBUG` | `0` olmalı. Açık kalırsa hata anında tarayıcıda çalışan Python konsolu açılır — yani uzaktan kod çalıştırma açığı |
| `DATA_DIR` | Veritabanı ve yüklenen dosyaların yazılacağı klasör. **Kalıcı bir diskte olmalı** |

Bunlar ayarlandıktan sonra uygulama her yerde aynı çalışır.

---

## PythonAnywhere (kredi kartı istemez)

Ücretsiz katmanda kalıcı disk var ve site 7/24 ayakta kalır. Docker kullanılmaz.

### 1. Hesap aç

[pythonanywhere.com](https://www.pythonanywhere.com) → **Create a Beginner account** (ücretsiz).

### 2. Kodu çek

**Consoles** → **Bash** ile bir konsol aç:

```bash
git clone https://github.com/SrknArda1/cv-platform.git
cd cv-platform

# Sanal ortam (KULLANICIADI yerine kendi kullanıcı adını yaz)
mkvirtualenv --python=/usr/bin/python3.10 kariyer
pip install -r requirements.txt
```

> `mkvirtualenv` ortamı otomatik etkinleştirir. Sonradan girmek için: `workon kariyer`

### 3. Veri klasörünü oluştur

Veritabanı ve yüklenen dosyalar **repo klasörünün dışında** durmalı; yoksa
`git pull` yaptığında karışır.

```bash
mkdir -p ~/kariyer-veri/uploads/transcripts ~/kariyer-veri/uploads/photos
```

### 4. Web uygulamasını tanımla

**Web** sekmesi → **Add a new web app**

- Framework: **Manual configuration** (Flask değil! Flask seçeneği kendi iskeletini kurar)
- Python sürümü: kurduğun sanal ortamla aynı (3.10)

Açılan sayfada:

- **Source code:** `/home/KULLANICIADI/cv-platform`
- **Virtualenv:** `/home/KULLANICIADI/.virtualenvs/kariyer`
- **Static files** (isteğe bağlı ama hızlandırır):
  - URL: `/static/` → Directory: `/home/KULLANICIADI/cv-platform/static/`

### 5. WSGI dosyasını düzenle

Aynı sayfada **WSGI configuration file** bağlantısına tıkla. İçindeki her şeyi
sil ve şunu yaz (üç yerdeki `KULLANICIADI` ve `SECRET_KEY` değerini değiştir):

```python
import os
import sys

path = "/home/KULLANICIADI/cv-platform"
if path not in sys.path:
    sys.path.insert(0, path)

# Uzun, rastgele bir değer. Konsolda üretebilirsin:
#   python -c "import secrets; print(secrets.token_hex(32))"
os.environ["SECRET_KEY"] = "BURAYA-UZUN-RASTGELE-BIR-DEGER"

os.environ["FLASK_DEBUG"] = "0"
os.environ["DATA_DIR"] = "/home/KULLANICIADI/kariyer-veri"

from app import app as application   # noqa: E402
```

> `SECRET_KEY` neden burada? PythonAnywhere ücretsiz katmanında ortam
> değişkeni arayüzü yok. Bu dosya repo dışında ve yalnızca senin
> hesabından okunabilir, bu yüzden git'e girmesinden daha güvenli.

### 6. Veritabanını hazırla

Bash konsoluna dön:

```bash
workon kariyer
cd ~/cv-platform

export DATA_DIR=~/kariyer-veri
export FLASK_DEBUG=0
export SECRET_KEY=gecici-sadece-bu-komutlar-icin

# Şema (ilk kurulum)
python -c "from app import create_app; create_app()"
flask --app app db stamp head

# Tanıtım verisi: 28 uydurma öğrenci, gerçek kişi yok
flask --app app seed-demo

# Yönetici hesabı
flask --app app create-admin
```

### 7. Yayına al

**Web** sekmesi → yeşil **Reload** düğmesi.

Adres: `https://KULLANICIADI.pythonanywhere.com`

### Sonraki güncellemeler

```bash
workon kariyer
cd ~/cv-platform
git pull
pip install -r requirements.txt          # yeni paket eklendiyse
export DATA_DIR=~/kariyer-veri
flask --app app db upgrade               # şema değiştiyse
```

Ardından **Web** sekmesinden **Reload**.

### Ücretsiz katmanın sınırları

- **3 ayda bir** Web sekmesinden "Run until 3 months from today" düğmesine
  basmak gerekir, yoksa site durur. E-posta hatırlatması gelir.
- Kendi alan adını bağlayamazsın.
- Günlük CPU kotası var; bu projede sorun çıkarmaz.

---

## Fly.io (kredi kartı ister)

Fly ücretsiz bir kota sunar ama **doğrulama için kart zorunludur** — kart
eklenmeden hiçbir makine açılamaz. Kart eklemeden `fly launch` çalıştırırsan
şu hatayı alırsın:

```
requested machine count exceeds organization limit
```

Kart eklendiyse gerekli dosyalar depoda hazır: `Dockerfile`, `start.sh`,
`fly.toml`, `.dockerignore`.

```powershell
fly launch --no-deploy        # mevcut fly.toml'u kullan (Yes de)
fly volumes create kariyer_veri --region ams --size 1
fly secrets set SECRET_KEY=$([Convert]::ToBase64String((1..48|%{Get-Random -Max 256})))
fly deploy

fly ssh console -C "flask --app app seed-demo"
fly ssh console               # açılan kabukta: flask --app app create-admin
```

**Volume olmadan dağıtmayın:** kabın kendi diski her yeniden başlatmada
sıfırlanır, veritabanı ve yüklenen transkriptler silinir.

---

## Gerçek kişisel veri asla sunucuya gitmez

Bu iki koruma birlikte çalışır:

| Dosya | Neyi engeller |
|---|---|
| `.gitignore` | Veritabanı ve yüklenen dosyalar **git'e** girmez |
| `.dockerignore` | Aynı dosyalar **Docker imajına** girmez |

İkisi ayrı ayrı gereklidir: `fly deploy` git'ten değil klasörden yükleme
yapar, yani `.gitignore` orada korumaz. PythonAnywhere'de ise kod `git clone`
ile geldiği için `.gitignore` yeterlidir.

Dağıtım her zaman **boş bir veritabanıyla** açılır; içeriği `seed-demo`
komutunun ürettiği tamamen kurgusal kayıtlardan oluşur. Örnek transkriptin
üzerinde "gerçek bir öğrenciye ait değildir" yazar.

> Bu iki dosyadan satır silmek gerçek kişisel veriyi internete açık bir
> sunucuya taşıyabilir. Değiştirmeden önce iki kez düşünün.
