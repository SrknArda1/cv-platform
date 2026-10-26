import os
from functools import wraps
from io import BytesIO
from datetime import datetime, timedelta
from urllib.parse import quote
import unicodedata
import re

from flask import Flask, render_template, redirect, url_for, request, flash, abort, send_from_directory, make_response
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa
from xhtml2pdf.default import DEFAULT_FONT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

import logging

from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, CSRFError
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from models import (db, User, Education, Experience, Certificate, Project,
                    Department, Message)
from api import api as api_blueprint, hata_yaniti as api_hata_yaniti

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Veritabani ve yuklenen dosyalar nereye yazilacak?
#
# Yerelde proje klasoru (varsayilan). Sunucuda ise kap (container) dosya
# sistemi her yeniden baslatmada sifirlandigi icin bunlarin KALICI bir
# diskte durmasi gerekir: Fly.io'da volume /data'ya baglanir ve
# DATA_DIR=/data verilir. Aksi halde her dagitimda veritabani ve
# yuklenen transkriptler silinir.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

# PDF fontlari.
#
# Sitedeki uc register PDF'te de karsiliksiz kalmasin diye ucu de kayitli:
#   serif -> belge basliklari      sans -> govde      mono -> tarih/etiket
# Fontlar projeye KOPYALANDI (static/fonts). Sistem fontuna guvenmek
# kirilgandir; sunucuda bulunmayabilir.
#
# NEDEN @font-face DEGIL:
# Sablonda @font-face kullanilirsa xhtml2pdf 0.2.16 font dosyasini once
# bir NamedTemporaryFile'a kopyalayip reportlab'e o gecici dosyanin ADINI
# veriyor. Windows acik bir gecici dosyanin adla yeniden acilmasina izin
# vermedigi icin uretim "TTFError: Can't open file" ile cokuyordu.
# Fontu dogrudan kaydedip xhtml2pdf'in font haritasina tanitinca gecici
# dosya hic olusmuyor; ayni kod Windows'ta ve Linux'ta calisiyor.
_FONT_KLASORU = os.path.join(BASE_DIR, "static", "fonts")
_FONT_YOLU = os.path.join(_FONT_KLASORU, "DejaVuSans.ttf")

_PDF_FONTLARI = [
    ("DejaVuSans",       "DejaVuSans.ttf"),
    ("DejaVuSans-Bold",  "DejaVuSans-Bold.ttf"),
    ("DejaVuSerif",      "DejaVuSerif.ttf"),
    ("DejaVuSerif-Bold", "DejaVuSerif-Bold.ttf"),
    ("DejaVuSansMono",   "DejaVuSansMono.ttf"),
]

try:
    for _ad, _dosya in _PDF_FONTLARI:
        pdfmetrics.registerFont(TTFont(_ad, os.path.join(_FONT_KLASORU, _dosya)))

    # Kalin yazim icin aile tanimi: <b> ve font-weight:bold bu esleme
    # sayesinde gercek kalin dosyaya gider, yapay kalinlastirmaya degil.
    pdfmetrics.registerFontFamily("DejaVuSans", normal="DejaVuSans", bold="DejaVuSans-Bold")
    pdfmetrics.registerFontFamily("DejaVuSerif", normal="DejaVuSerif", bold="DejaVuSerif-Bold")

    # xhtml2pdf font adlarini kucuk harfe cevirerek arar
    DEFAULT_FONT["dejavusans"] = "DejaVuSans"
    DEFAULT_FONT["dejavuserif"] = "DejaVuSerif"
    DEFAULT_FONT["dejavusansmono"] = "DejaVuSansMono"
except Exception as _font_hata:        # font yoksa PDF yine uretilir, varsayilana duser
    print(f"[uyari] PDF fontu yuklenemedi: {_font_hata}")

TRANSCRIPT_FOLDER = os.path.join(DATA_DIR, "uploads", "transcripts")
PHOTO_FOLDER = os.path.join(DATA_DIR, "uploads", "photos")

ALLOWED_TRANSCRIPT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-anahtari-degistir")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DATA_DIR, "cv_platform.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = TRANSCRIPT_FOLDER
app.config["PHOTO_FOLDER"] = PHOTO_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

# --- Oturum cerezi sertlestirmesi ---
#
# HTTPONLY  : cerez JavaScript'ten okunamaz (XSS ile oturum calinmasini zorlastirir)
# SECURE    : cerez yalnizca HTTPS uzerinden gonderilir. Yerelde http://127.0.0.1
#             kullandigimiz icin sadece disa acik calistirmada (FLASK_DEBUG=0) acilir,
#             aksi halde yerelde hic giris yapilamazdi.
# SAMESITE  : baska bir siteden gelen isteklere cerez eklenmez; CSRF'e ikinci savunma.
# LIFETIME  : oturum 31 gun degil 8 saat yasar. Yonetici bilgisayarini acik
#             biraktiginda riskin suresini kisaltir.
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_DEBUG", "1") == "0"
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=8)

# Giris denemelerini goruntulemek icin basit log. Sunucu ciktisinda
# (PythonAnywhere error log / fly logs) gorunur.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
guvenlik_log = logging.getLogger("guvenlik")

# Uygulama bir vekil sunucunun (PythonAnywhere / Fly nginx) arkasinda
# calisiyor. ProxyFix olmadan Flask her istegin VEKIL SUNUCUDAN geldigini
# sanir; o zaman "IP basina 10 giris/dakika" sinirimiz IP basina degil
# TUM SITE icin gecerli olur ve tek bir kullanici herkesi kilitleyebilir.
# x_for=1: yalnizca en son vekilin ekledigi IP'ye guvenilir. Daha fazlasina
# guvenmek, istemcinin X-Forwarded-For basligini uydurmasina izin verirdi.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# CSRF (siteler arasi istek sahteciligi) korumasi.
#
# Koruma olmadan, giris yapmis bir kullanici kotu niyetli bir sayfayi
# ziyaret ettiginde o sayfa onun adina bu siteye POST gonderebilir:
# yonetici farkinda olmadan bir kurumu onaylayabilir, ogrenci CV'si
# degistirilebilirdi. CSRFProtect her POST/PUT/DELETE istegine gizli bir
# token sartı koyar; token yalnizca bizim sayfalarimizda uretildigi icin
# baska bir site bunu taklit edemez.
#
# Token sablonlara {{ csrf_token() }} ile gelir ve SECRET_KEY ile imzalanir.
csrf = CSRFProtect(app)

# --- Giris denemesi sinirlamasi (brute-force korumasi) ---
#
# Sinirlama olmadan bir betik dakikada binlerce sifre deneyebilir; zayif bir
# sifre saniyeler icinde kirilir. Adresin gizli olmasi koruma degildir,
# /admin/giris tahmin edilebilir bir adrestir. Asil engel budur.
#
# storage_uri="memory://": sayaclar surecin belleginde tutulur. Tek islemli
# calistirmada (PythonAnywhere ucretsiz katman, gunicorn --workers 2) yeterli.
# Cok sunuculu bir kuruluma gecilirse Redis'e alinmalidir, yoksa her sunucu
# kendi sayacini tutar ve sinir etkisini kaybeder.
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    strategy="fixed-window",
)

db.init_app(app)

# render_as_batch: SQLite ALTER TABLE'i cok sinirli destekler (kolon silme,
# kisit degistirme yok). Alembic bu modda tabloyu gecici bir kopyaya tasiyip
# yeniden olusturur; SQLite'ta migrasyon icin pratikte zorunludur.
migrate = Migrate(app, db, render_as_batch=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# Kayit formlari icin ortak dogrulama kurallari.
#
# Tarayicinin type="email" kontrolu yeterli degil: HTML5 "ad@gmail" gibi
# TLD'siz adresleri GECERLI sayar. Canli sistemde boyle bir kayit olustu.
# Sunucu tarafinda da kontrol sart -- istemci kontrolu her zaman atlanabilir.
EPOSTA_DESENI = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

SIFRE_EN_AZ = 6


def kayit_dogrula(email, sifre, sifre_tekrar):
    """Kayit alanlarini dogrular; sorun varsa mesaji, yoksa None doner."""
    if not EPOSTA_DESENI.match(email):
        return "Geçerli bir e-posta adresi girin (örnek: ad.soyad@ornek.com)."
    if len(sifre) < SIFRE_EN_AZ:
        return f"Şifre en az {SIFRE_EN_AZ} karakter olmalı."
    if sifre != sifre_tekrar:
        return "Şifreler eşleşmiyor. Lütfen ikisini de kontrol edin."
    return None


def dosyayi_sil(klasor, dosya_adi):
    """Yuklenen bir dosyayi diskten siler.

    Dosya zaten yoksa sessizce gecer. Veritabani kaydini silmek yetmez:
    kayit silinse de dosya diskte kalirsa ogrencinin transkripti sunucuda
    durmaya devam eder.
    """
    if not dosya_adi:
        return
    try:
        os.remove(os.path.join(klasor, dosya_adi))
    except OSError:
        pass


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_TRANSCRIPT_EXTENSIONS


def allowed_photo(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


def role_required(*roles):
    """Sayfayi yalnizca belirtilen rollere acar.

    Birden fazla rol verilebilir: role_required("company", "admin").
    Yonetici, transkripti dogrulayabilmek icin kurum sayfalarindan bazilarina
    (CV goruntuleme, transkript acma) erismek zorunda.
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


# Ogrencinin girdigi adresler sablonda href="" icine yaziliyor. Jinja
# ozel karakterleri kacirir ama SEMAYI denetlemez: "javascript:..." yazan bir
# ogrencinin baglantisina tiklayan kurum, o kodu kendi oturumunda calistirir.
# O yuzden yalnizca http/https gecer. Ayrica insanlar adresi cogu zaman
# "credly.com/..." diye semasiz yaziyor; onu reddetmek yerine https ekliyoruz.
IZINLI_SEMALAR = ("http://", "https://")


def guvenli_baglanti(adres):
    """Gosterilmesi guvenli bir http(s) adresi veya bos dize doner."""
    adres = (adres or "").strip()
    if not adres:
        return ""
    if adres.lower().startswith(IZINLI_SEMALAR):
        return adres
    # Sema yok: ":" varsa bu baska bir sema denemesidir (javascript:, data:),
    # atilir. Yoksa kullanici sadece alan adini yazmis, https ekliyoruz.
    if ":" in adres.split("/", 1)[0]:
        return ""
    return "https://" + adres


def parse_dynamic_rows(prefix, fields, required_field):
    lists = {f: request.form.getlist(f"{prefix}_{f}[]") for f in fields}
    length = max((len(v) for v in lists.values()), default=0)
    rows = []
    for i in range(length):
        row = {f: (lists[f][i].strip() if i < len(lists[f]) else "") for f in fields}
        if row.get(required_field):
            rows.append(row)
    return rows


def seed_departments():
    """Tabloda bölüm yoksa ilk açılışta deneme bölümlerini yükler."""
    initial_departments = [
        "Fiber Teknolojisi",
        "Kurumsal Bilişim"
    ]
    for dept_name in initial_departments:
        if not Department.query.filter_by(name=dept_name).first():
            db.session.add(Department(name=dept_name))
    db.session.commit()


# ---------- Genel sayfalar ve Medya ----------

@app.context_processor
def inject_globals():
    """Her sablonda kullanilabilen degerler (footer telif yili gibi)."""
    return {"now_year": datetime.now().year}


# ---------- Hata sayfalari ----------
# Varsayilan Flask sayfalari stilsiz geliyor; tasarim sistemiyle ayni
# kabukta gosterilsinler diye tek bir sablona baglandilar.

def _error_page(code, title, text):
    # /api/ altindaki hatalar HTML sayfasi degil JSON donmeli: istemcinin
    # ayristiricisi HTML gorurse coker. Bu TEK kontrol asagidaki butun
    # errorhandler'lari kapsiyor -- her birine ayri ayri eklemeye gerek yok.
    if request.path.startswith("/api/v1"):
        return api_hata_yaniti(code, title, text)
    return render_template("error.html", code=code, title=title, text=text), code


@app.errorhandler(403)
def error_forbidden(e):
    return _error_page(
        403, "Bu sayfaya erişiminiz yok",
        "Bu bölüm başka bir hesap türü için. Öğrenci hesabıyla kurum sayfalarına "
        "(veya tersi) girilemez.",
    )


@app.errorhandler(404)
def error_not_found(e):
    return _error_page(
        404, "Sayfa bulunamadı",
        "Aradığınız adres değişmiş ya da hiç var olmamış olabilir.",
    )


@app.errorhandler(CSRFError)
def error_csrf(e):
    """CSRF token eksik veya gecersiz.

    Gercek bir saldiri olabilir; ama cok daha sik rastlanan sebep, formun
    uzun sure acik kalip oturumun zaman asimina ugramasidir. Mesaj bu
    yuzden sucgucu degil yol gosterici.
    """
    return _error_page(
        400, "Form gönderilemedi",
        "Güvenlik doğrulaması geçersiz. Form uzun süre açık kaldıysa oturumunuz "
        "zaman aşımına uğramış olabilir. Sayfayı yenileyip tekrar deneyin.",
    )


@app.errorhandler(429)
def error_too_many_requests(e):
    return _error_page(
        429, "Çok fazla deneme",
        "Arka arkaya çok sayıda giriş denemesi yapıldı. Güvenlik gereği bir "
        "süre beklemeniz gerekiyor; birkaç dakika sonra tekrar deneyin.",
    )


@app.errorhandler(413)
def error_too_large(e):
    return _error_page(
        413, "Dosya çok büyük",
        "Yüklediğiniz dosya 10 MB sınırını aşıyor. Daha küçük bir dosya seçip "
        "tekrar deneyin.",
    )


@app.errorhandler(500)
def error_server(e):
    return _error_page(
        500, "Bir şeyler ters gitti",
        "Sunucuda beklenmedik bir hata oluştu. Lütfen biraz sonra tekrar deneyin.",
    )


@app.route("/kvkk")
def kvkk():
    return render_template("kvkk.html")


@app.route("/api")
def api_docs():
    """API'nin insan yuzu.

    /api/v1 altindaki uc noktalar JSON doner ve tarayicida ciplak metin gibi
    gorunur. Bu sayfa onlari listeler, ne dondurduklerini anlatir ve indirme
    baglantilari verir -- gercek API'lerdeki Swagger/Redoc belgesinin
    karsiligi. Adres bilerek /api: /api/v1 ile karismaz, tahmin edilmesi
    kolaydir.
    """
    uclar = [
        {"yol": "/api/v1/", "csv": False,
         "aciklama": "API'nin kendini tanitmasi: adres listesi, filtreler ve CSV kullanimi."},
        {"yol": "/api/v1/ozet", "csv": False,
         "aciklama": "Ogrenci, kurum ve sertifika sayimlari tek bakista."},
        {"yol": "/api/v1/ogrenciler", "csv": True,
         "aciklama": "Anonim ogrenci kayitlari. 13 alan, sayfalanmis ve filtrelenebilir."},
        {"yol": "/api/v1/bolumler", "csv": True,
         "aciklama": "Bolum bazinda ogrenci sayisi, ortalama not ve profil dolulugu."},
        {"yol": "/api/v1/yetkinlikler", "csv": True,
         "aciklama": "Hangi yetkinligin kac ogrencide gectigi, azalan sirada."},
    ]
    sayim = {
        "ogrenci": User.query.filter_by(role="student").count(),
        "bolum": Department.query.count(),
        "sertifika": Certificate.query.count(),
    }
    return render_template("api_docs.html", uclar=uclar, sayim=sayim,
                           taban=request.url_root.rstrip("/"))


@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "student":
            return redirect(url_for("student_dashboard"))
        if current_user.role == "admin":
            return redirect(url_for("admin_overview"))
        return redirect(url_for("company_dashboard"))
    return render_template("index.html")


@app.route("/uploads/photos/<filename>")
@login_required
def uploaded_photo(filename):
    """Profil fotografi.

    login_required sart: dosya adi photo_<kullanici_id>_<zaman>.png
    bicimindedir, yani tahmin edilebilir. Koruma olmadan adresi bilen
    herkes ogrencilerin fotografini indirebiliyordu. Fotograf zaten
    yalnizca girisli sayfalarda gosteriliyor, bu yuzden bir sey bozulmaz.
    """
    return send_from_directory(app.config["PHOTO_FOLDER"], filename)


# ---------- Öğrenci: kayıt / giriş ----------

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        full_name = request.form.get("full_name", "").strip()

        # Hata durumunda girilen bilgiler kaybolmasin diye sayfa yeniden
        # cizilir (yonlendirme yapilmaz); sifreler bilerek tasinmaz.
        def hatayla_don(mesaj):
            flash(mesaj, "error")
            return render_template("student_register.html", girilen=request.form), 400

        if not email or not password or not full_name:
            return hatayla_don("Lütfen tüm alanları doldurun.")

        hata = kayit_dogrula(email, password, password2)
        if hata:
            return hatayla_don(hata)

        if User.query.filter_by(email=email).first():
            return hatayla_don("Bu e-posta ile zaten bir hesap var.")

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role="student",
            full_name=full_name,
            is_approved=True  # Öğrenci doğrudan aktif
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Kayıt başarılı, şimdi özgeçmiş bilgilerinizi girebilirsiniz.", "success")
        return redirect(url_for("student_cv_form"))

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
# Kampus aginda onlarca ogrenci AYNI dis IP'yi paylasir (NAT). Sinir cok
# darsa toplu veri girisi sirasinda gercek kullanicilar kilitlenir. Bu
# deger otomatik sozluk saldirisini hala engeller (saniyede yuzlerce
# deneme yapilamaz) ama bir sinifin ayni anda giris yapmasina izin verir.
@limiter.limit("60 per minute; 400 per hour", methods=["POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="student").first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("student_dashboard"))

        guvenlik_log.warning(
            "Basarisiz ogrenci girisi: %s (IP: %s)", email, get_remote_address())
        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("student_login"))

    return render_template("student_login.html")


# ---------- Öğrenci: dashboard / CV formu ----------

@app.route("/student/dashboard")
@login_required
@role_required("student")
def student_dashboard():
    return render_template("student_dashboard.html", student=current_user)


@app.route("/student/cv", methods=["GET", "POST"])
@login_required
@role_required("student")
def student_cv_form():
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.department = request.form.get("department", "").strip()
        current_user.phone = request.form.get("phone", "").strip()
        current_user.summary = request.form.get("summary", "").strip()
        current_user.skills = request.form.get("skills", "").strip()

        # Profil Fotoğrafı: kaldırma ya da yükleme
        photo = request.files.get("photo")
        if request.form.get("remove_photo") == "1":
            dosyayi_sil(app.config["PHOTO_FOLDER"], current_user.photo_filename)
            current_user.photo_filename = None
        elif photo and photo.filename:
            if not allowed_photo(photo.filename):
                flash("Fotoğraf için sadece JPG, PNG veya WEBP yükleyebilirsiniz.", "error")
                return redirect(url_for("student_cv_form"))
            ext = photo.filename.rsplit(".", 1)[1].lower()
            photo_filename = secure_filename(f"photo_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}")
            # Dosya adinda zaman damgasi var, yani her yukleme YENI bir ad
            # uretir. Eskisi elle silinmezse diskte sonsuza kadar kalir.
            eski = current_user.photo_filename
            photo.save(os.path.join(app.config["PHOTO_FOLDER"], photo_filename))
            current_user.photo_filename = photo_filename
            if eski and eski != photo_filename:
                dosyayi_sil(app.config["PHOTO_FOLDER"], eski)

        # Transkript: kaldırma ya da yükleme
        file = request.files.get("transcript")
        if request.form.get("remove_transcript") == "1":
            dosyayi_sil(app.config["UPLOAD_FOLDER"], current_user.transcript_filename)
            current_user.transcript_filename = None
            # Belge gidince doğrulama da anlamsız kalır
            current_user.transcript_verified = False
            current_user.transcript_verified_at = None
            current_user.transcript_verified_by_id = None
        elif file and file.filename:
            if not allowed_file(file.filename):
                flash("Sadece PDF, JPG veya PNG dosyası yükleyebilirsiniz.", "error")
                return redirect(url_for("student_cv_form"))
            ext = file.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"transcript_{current_user.id}.{ext}")
            # Uzanti degisirse (.pdf -> .png) ad da degisir ve eski dosya
            # diskte kalir; o yuzden yenisini yazmadan once eskisi silinir.
            eski = current_user.transcript_filename
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            current_user.transcript_filename = filename
            if eski and eski != filename:
                dosyayi_sil(app.config["UPLOAD_FOLDER"], eski)

            # Yeni belge yuklendi: onceki dogrulama artik gecersiz.
            # Bu sifirlama olmadan ogrenci dogrulanmis transkripti baska bir
            # dosyayla degistirip "dogrulandi" rozetini tasimaya devam
            # edebilirdi -- dogrulamanin tum anlamini bosa cikarirdi.
            current_user.transcript_verified = False
            current_user.transcript_verified_at = None
            current_user.transcript_verified_by_id = None

        # Dinamik bölümleri sıfırlayıp yeniden oluştur
        Education.query.filter_by(student_id=current_user.id).delete()
        Experience.query.filter_by(student_id=current_user.id).delete()
        Certificate.query.filter_by(student_id=current_user.id).delete()
        Project.query.filter_by(student_id=current_user.id).delete()

        for row in parse_dynamic_rows(
            "edu", ["degree_type", "school", "department", "gpa", "start_year", "end_year"], "school"
        ):
            db.session.add(Education(student_id=current_user.id, **row))
            
        for row in parse_dynamic_rows(
            "exp", ["company", "position", "start_date", "end_date", "description"], "company"
        ):
            db.session.add(Experience(student_id=current_user.id, **row))

        for row in parse_dynamic_rows(
            "cert", ["name", "institution", "date", "credential_id", "credential_url"], "name"
        ):
            row["credential_url"] = guvenli_baglanti(row["credential_url"])
            db.session.add(Certificate(student_id=current_user.id, **row))

        for row in parse_dynamic_rows(
            "proj", ["title", "description", "tech_stack", "link"], "title"
        ):
            row["link"] = guvenli_baglanti(row["link"])
            db.session.add(Project(student_id=current_user.id, **row))

        db.session.commit()
        flash("Özgeçmişiniz güncellendi.", "success")
        return redirect(url_for("student_dashboard"))

    return render_template("student_cv_form.html", student=current_user, departments=departments)


@app.route("/student/preview")
@login_required
@role_required("student")
def student_preview():
    return render_template("cv_detail.html", student=current_user, is_own_preview=True)


# ---------- Kurum: kayıt / giriş ----------

@app.route("/company/register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        company_name = request.form.get("company_name", "").strip()
        contact_person = request.form.get("contact_person", "").strip()

        def hatayla_don(mesaj):
            flash(mesaj, "error")
            return render_template("company_register.html", girilen=request.form), 400

        if not email or not password or not company_name:
            return hatayla_don("Lütfen tüm alanları doldurun.")

        hata = kayit_dogrula(email, password, password2)
        if hata:
            return hatayla_don(hata)

        if User.query.filter_by(email=email).first():
            return hatayla_don("Bu e-posta ile zaten bir hesap var.")

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role="company",
            company_name=company_name,
            contact_person=contact_person,
            is_approved=False  # <-- Yönetici onayı bekleyecek
        )
        db.session.add(user)
        db.session.commit()
        
        flash("Kurum kaydınız alındı. Kariyer Merkezi/Yönetici onayından sonra aday havuzuna erişebilirsiniz.", "info")
        return redirect(url_for("company_login"))

    return render_template("company_register.html")

@app.route("/company/login", methods=["GET", "POST"])
# Kampus aginda onlarca ogrenci AYNI dis IP'yi paylasir (NAT). Sinir cok
# darsa toplu veri girisi sirasinda gercek kullanicilar kilitlenir. Bu
# deger otomatik sozluk saldirisini hala engeller (saniyede yuzlerce
# deneme yapilamaz) ama bir sinifin ayni anda giris yapmasina izin verir.
@limiter.limit("60 per minute; 400 per hour", methods=["POST"])
def company_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="company").first()

        if user and check_password_hash(user.password_hash, password):
            if user.basvuru_durumu == "reddedildi":
                mesaj = "Başvurunuz kampüs koordinatörü tarafından reddedildi."
                if user.rejection_reason:
                    mesaj += f" Gerekçe: {user.rejection_reason}"
                flash(mesaj, "error")
                return redirect(url_for("company_login"))

            if not user.is_approved:
                flash("Hesabınız henüz onaylanmadı. Kampüs koordinatörünün onayını bekleyiniz.", "error")
                return redirect(url_for("company_login"))

            login_user(user)
            return redirect(url_for("company_dashboard"))

        guvenlik_log.warning(
            "Basarisiz kurum girisi: %s (IP: %s)", email, get_remote_address())
        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("company_login"))

    return render_template("company_login.html")


@app.route("/company/profil", methods=["GET", "POST"])
@login_required
@role_required("company")
def company_profile():
    """Kurumun kendi profili.

    `focus_skills` burada doldurulur ve aday havuzunda tek tikla filtreye
    donusur: kurum "Network, Linux" yazdiysa, havuzda bu yetkinliklere
    sahip adaylari dogrudan suzebilir. Bolum bazli aramadan cok daha dar
    bir eslestirme saglar.
    """
    if request.method == "POST":
        current_user.company_name = request.form.get("company_name", "").strip() or current_user.company_name
        current_user.contact_person = request.form.get("contact_person", "").strip() or None
        current_user.sector = request.form.get("sector", "").strip()[:160] or None
        current_user.website = request.form.get("website", "").strip()[:255] or None
        current_user.about = request.form.get("about", "").strip() or None

        # Yetkinlikleri normalize et: fazla bosluk ve tekrarlari temizle
        ham = request.form.get("focus_skills", "")
        temiz, gorulen = [], set()
        for parca in ham.split(","):
            parca = parca.strip()
            if parca and parca.casefold() not in gorulen:
                gorulen.add(parca.casefold())
                temiz.append(parca)
        current_user.focus_skills = ", ".join(temiz)[:400] or None

        db.session.commit()
        flash("Kurum profiliniz güncellendi.", "success")
        return redirect(url_for("company_profile"))

    return render_template("company_profile.html")


# ---------- Kurum: aday havuzu & İndirme ----------

# Aday havuzunda sıralanabilir kolonlar.
# Her kolon için iki fonksiyon: (sıralama değeri, değer eksik mi?)
# Ortalama ve doluluk yüzdesi SQL'de değil Python'da hesaplanıyor (biri metin
# alanından parse ediliyor, diğeri ilişkilere bakan bir metot), bu yüzden
# sıralamanın tamamı Python tarafında yapılır.
CANDIDATE_SORTERS = {
    "name":        (lambda s: (s.full_name or "").casefold(), lambda s: not (s.full_name or "").strip()),
    "department":  (lambda s: (s.department or "").casefold(), lambda s: not (s.department or "").strip()),
    "gpa":         (lambda s: s.gpa_value or 0.0, lambda s: s.gpa_value is None),
    "experience":  (lambda s: len(s.experiences), lambda s: False),
    "project":     (lambda s: len(s.projects), lambda s: False),
    "certificate": (lambda s: len(s.certificates), lambda s: False),
    "transcript":  (lambda s: (bool(s.transcript_filename), s.transcript_verified),
                    lambda s: False),
    "completion":  (lambda s: s.profile_completion(), lambda s: False),
    "created":     (lambda s: s.created_at or datetime.min, lambda s: s.created_at is None),
}

# Aday havuzunda sayfa basina kayit sayisi
CANDIDATES_PER_PAGE = 25


@app.route("/company/dashboard")
@login_required
@role_required("company")
def company_dashboard():
    selected_department = request.args.get("department", "")
    q = request.args.get("q", "").strip()
    only_with_transcript = request.args.get("has_transcript") == "1"
    only_verified = request.args.get("verified") == "1"
    # Yetkinlik filtresi: "Network" gibi tek bir beceri, ya da kurumun
    # profilindeki aranan yetkinliklerin tamami ("odak" modu).
    skill = request.args.get("skill", "").strip()
    use_focus = request.args.get("focus") == "1"

    try:
        min_completion = int(request.args.get("min_completion", 0))
    except ValueError:
        min_completion = 0

    sort = request.args.get("sort", "name")
    if sort not in CANDIDATE_SORTERS:
        sort = "name"
    direction = "desc" if request.args.get("dir") == "desc" else "asc"

    query = User.query.filter_by(role="student")
    if selected_department:
        query = query.filter_by(department=selected_department)
    if q:
        # İsim, e-posta ve yetkinliklerde birlikte ara
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.skills.ilike(like),
            )
        )
    if only_with_transcript:
        query = query.filter(User.transcript_filename.isnot(None))
    if only_verified:
        query = query.filter(User.transcript_verified.is_(True))

    if skill:
        query = query.filter(User.skills.ilike(f"%{skill}%"))
    elif use_focus and current_user.focus_list:
        # Kurumun aradigi yetkinliklerden EN AZ BIRINE sahip adaylar.
        # "hepsine sahip" degil: tek bir eksik beceri iyi bir adayi
        # listeden dusurur, bu da aramayi fazla daraltirdi.
        query = query.filter(db.or_(
            *[User.skills.ilike(f"%{y}%") for y in current_user.focus_list]
        ))

    students = query.all()
    total_students = User.query.filter_by(role="student").count()

    if min_completion:
        students = [s for s in students if s.profile_completion() >= min_completion]

    # İki aşamalı kararlı sıralama: önce değere göre, sonra "eksik olanlar
    # en sona" diye. Python'un sort'u kararlı olduğu için yön ne olursa olsun
    # ortalaması girilmemiş adaylar listenin sonunda kalır.
    value_of, is_missing = CANDIDATE_SORTERS[sort]
    students.sort(key=value_of, reverse=(direction == "desc"))
    students.sort(key=is_missing)

    # Sayfalama: siralama Python tarafinda yapildigi icin dilimleme de burada.
    # Istenen sayfa aralik disindaysa son sayfaya kirpilir, hata vermez.
    match_count = len(students)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    page_count = max(1, -(-match_count // CANDIDATES_PER_PAGE))
    page = min(page, page_count)
    start = (page - 1) * CANDIDATES_PER_PAGE
    students = students[start:start + CANDIDATES_PER_PAGE]

    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "company_dashboard.html",
        students=students,
        departments=departments,
        selected_department=selected_department,
        q=q,
        only_with_transcript=only_with_transcript,
        only_verified=only_verified,
        skill=skill,
        use_focus=use_focus,
        min_completion=min_completion,
        sort=sort,
        direction=direction,
        total_students=total_students,
        match_count=match_count,
        page=page,
        page_count=page_count,
        range_start=start + 1 if match_count else 0,
        range_end=start + len(students),
    )


@app.route("/company/student/<int:student_id>")
@login_required
@role_required("company", "admin")
def student_detail(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    return render_template("cv_detail.html", student=student, is_own_preview=False)


@app.route("/company/student/<int:student_id>/pdf")
@app.route("/student/cv-pdf", endpoint="download_own_cv_pdf")
@login_required
def download_student_cv_pdf(student_id=None):
    """CV'yi PDF olarak indirir.

    Kurum ve yonetici herhangi bir adayin CV'sini; ogrenci YALNIZCA kendi
    CV'sini indirebilir. Ogrenciler icin /student/cv-pdf kisayolu var,
    boylece adres cubugunda /company/... gormuyorlar.
    """
    if student_id is None:                       # /student/cv-pdf
        student_id = current_user.id

    if current_user.role == "student":
        if current_user.id != student_id:
            abort(403)
    elif current_user.role not in ("company", "admin"):
        abort(403)

    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    
    # Fotograf yalnizca PDF kutuphanesinin acabilecegi bicimdeyse gonderilir.
    # Ucu de test edildi: png, jpg ve webp sorunsuz gomuluyor. Liste yine de
    # acik tutuluyor cunku desteklenmeyen bir bicim PDF uretimini tamamen
    # cokertir; resimsiz bir CV, hata sayfasindan iyidir.
    PDF_RESIM_BICIMLERI = (".png", ".jpg", ".jpeg", ".webp")
    foto = student.photo_filename
    if foto:
        uygun = foto.lower().endswith(PDF_RESIM_BICIMLERI)
        varmi = os.path.exists(os.path.join(PHOTO_FOLDER, foto))
        if not (uygun and varmi):
            foto = None

    html_content = render_template("cv_pdf.html", student=student, foto=foto)
    pdf_buffer = BytesIO()
    
    def link_callback(uri, rel):
        """Sablondaki goreli yollari diskteki gercek dosyaya cevirir.

        Profil fotograflari static/ altinda DEGIL, DATA_DIR altindaki
        uploads/photos klasorunde duruyor (kalici disk). Bu yuzden ayri
        ele alinmalari gerekiyor; yoksa xhtml2pdf dosyayi bulamaz ve
        resim PDF'e hic girmez.
        """
        if uri.startswith("uploads/photos/"):
            return os.path.join(PHOTO_FOLDER, os.path.basename(uri))
        if uri.startswith("static/"):
            return os.path.join(BASE_DIR, uri)
        return os.path.join(BASE_DIR, "static", uri)

    pisa_status = pisa.CreatePDF(
        src=html_content,
        dest=pdf_buffer,
        encoding="utf-8",
        link_callback=link_callback
    )
    
    if pisa_status.err:
        flash("PDF oluşturulurken bir hata meydana geldi.", "error")
        return redirect(url_for("student_detail", student_id=student.id))
        
    pdf_data = pdf_buffer.getvalue()

    raw_name = student.full_name or "Ogrenci"
    clean_name = unicodedata.normalize("NFKD", raw_name).encode("ASCII", "ignore").decode("utf-8")
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name.strip())
    ascii_filename = f"CV_{clean_name or 'Ogrenci'}.pdf"
    utf8_filename = quote(f"CV_{raw_name}.pdf")
    
    response = make_response(pdf_data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"
    return response


@app.route("/company/transcript/<int:student_id>")
@login_required
@role_required("company", "admin")
def download_transcript(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    if not student.transcript_filename:
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], student.transcript_filename)


@app.route("/student/transcript")
@login_required
@role_required("student")
def download_own_transcript():
    if not current_user.transcript_filename:
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], current_user.transcript_filename)


# ---------- Mesajlaşma ----------
#
# Kim kime BASLATABILIR:
#   kurum  -> ogrenci    (onayli kurum, bir adayi gorup iletisime gecer)
#   herkes -> yonetici   (destek)
#   yonetici -> herkes
#   ogrenci -> kurum     yalnizca CEVAP olarak (once kurum yazmis olmali)
#
# Ogrencinin kuruma kendiliginden yazamamasinin sebebi: ogrenci kurum
# listesini zaten gormuyor, ve bu kisit istenmeyen mesaji bastan engelliyor.


def mesaj_atabilir_mi(gonderen, alici):
    """gonderen, alici'ya YENI bir konusma baslatabilir mi?"""
    if gonderen.id == alici.id:
        return False

    # Yonetici her iki yonde de serbest (destek kanali)
    if gonderen.role == "admin" or alici.role == "admin":
        return True

    # Kurum -> ogrenci: kurumun onayli olmasi sart
    if gonderen.role == "company" and alici.role == "student":
        return gonderen.is_approved

    # Ogrenci -> kurum: yalnizca o kurum daha once yazmissa (cevap)
    if gonderen.role == "student" and alici.role == "company":
        return Message.query.filter_by(
            sender_id=alici.id, recipient_id=gonderen.id
        ).first() is not None

    return False


def konusma_sorgusu(a_id, b_id):
    """Iki kullanici arasindaki tum mesajlar (her iki yon)."""
    return Message.query.filter(
        db.or_(
            db.and_(Message.sender_id == a_id, Message.recipient_id == b_id),
            db.and_(Message.sender_id == b_id, Message.recipient_id == a_id),
        )
    )


@app.context_processor
def inject_unread():
    """Üst menüdeki okunmamış sayısı. Her şablonda kullanılabilir."""
    if not current_user.is_authenticated:
        return {"okunmamis_mesaj": 0}
    return {"okunmamis_mesaj": Message.query.filter_by(
        recipient_id=current_user.id, read_at=None).count()}


@app.route("/mesajlar")
@login_required
def messages_inbox():
    uid = current_user.id
    hepsi = (Message.query
             .filter(db.or_(Message.sender_id == uid, Message.recipient_id == uid))
             .order_by(Message.created_at.desc())
             .all())

    # En yeniden eskiye gidildigi icin her kisinin ILK gorulen mesaji son mesajidir
    konusmalar = {}
    for m in hepsi:
        diger_id = m.recipient_id if m.sender_id == uid else m.sender_id
        if diger_id not in konusmalar:
            konusmalar[diger_id] = {"kisi": m.karsi_taraf(uid), "son": m, "okunmamis": 0}
        if m.recipient_id == uid and m.read_at is None:
            konusmalar[diger_id]["okunmamis"] += 1

    return render_template("messages_inbox.html", konusmalar=list(konusmalar.values()))


@app.route("/mesajlar/<int:user_id>", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per minute", methods=["POST"])
def messages_thread(user_id):
    diger = User.query.get_or_404(user_id)
    if diger.id == current_user.id:
        abort(403)

    var_olan = konusma_sorgusu(current_user.id, diger.id).first()

    # Konusma yoksa yeni baslatma izni aranir; varsa taraflar devam edebilir.
    if not var_olan and not mesaj_atabilir_mi(current_user, diger):
        abort(403)

    if request.method == "POST":
        govde = request.form.get("body", "").strip()
        if not govde:
            flash("Boş mesaj gönderilemez.", "error")
        elif len(govde) > 4000:
            flash("Mesaj çok uzun (en fazla 4000 karakter).", "error")
        else:
            db.session.add(Message(
                sender_id=current_user.id, recipient_id=diger.id, body=govde))
            db.session.commit()
        return redirect(url_for("messages_thread", user_id=diger.id))

    mesajlar = konusma_sorgusu(current_user.id, diger.id).order_by(Message.created_at).all()

    # Acilan konusmadaki okunmamislari okundu isaretle
    okunmamis = [m for m in mesajlar if m.recipient_id == current_user.id and m.read_at is None]
    if okunmamis:
        simdi = datetime.now()
        for m in okunmamis:
            m.read_at = simdi
        db.session.commit()

    return render_template("messages_thread.html", diger=diger, mesajlar=mesajlar)


# ---------- Yönetici (kampüs koordinatörü) ----------
#
# Kurum hesaplari is_approved=False olarak dogar ve onaylanmadan giris
# yapamaz. Onay, bugune kadar yalnizca "flask approve-company" komutuyla
# veriliyordu; buradaki ekranlar ayni isi tarayicidan yapar.
#
# Yonetici hesabi tarayicidan ACILAMAZ: kayit sayfasi yoktur, yalnizca
# "flask create-admin" komutuyla olusturulur. Aksi halde isteyen herkes
# yonetici olup butun ogrenci verisine erisebilirdi.


# Yonetici girisi en dar sinira tabi: tek bir hesap var, mesru kullanici
# gunde birkac kez giriyor. Saldirgan icin ise 5 deneme/dakika, sozluk
# saldirisini pratikte imkansiz hale getirir.
@app.route("/admin/giris", methods=["GET", "POST"])
@limiter.limit("15 per minute; 60 per hour", methods=["POST"])
def admin_login():
    if current_user.is_authenticated and current_user.role == "admin":
        return redirect(url_for("admin_overview"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email, role="admin").first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            guvenlik_log.info(
                "Yonetici girisi: %s (IP: %s)", email, get_remote_address())
            return redirect(url_for("admin_overview"))

        # Yonetici hesabina yonelik denemeler ayrica dikkat cekici
        guvenlik_log.warning(
            "BASARISIZ YONETICI GIRISI: %s (IP: %s)", email, get_remote_address())
        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/kurumlar")
@login_required
@role_required("admin")
def admin_companies():
    companies = User.query.filter_by(role="company").order_by(User.created_at.desc()).all()
    pending = [c for c in companies if c.basvuru_durumu == "bekliyor"]
    approved = [c for c in companies if c.basvuru_durumu == "onayli"]
    rejected = [c for c in companies if c.basvuru_durumu == "reddedildi"]
    return render_template(
        "admin_companies.html", pending=pending, approved=approved, rejected=rejected
    )


@app.route("/admin/kurumlar/<int:company_id>/onayla", methods=["POST"])
@login_required
@role_required("admin")
def admin_approve_company(company_id):
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    company.is_approved = True
    company.approved_at = datetime.now()
    company.approved_by_id = current_user.id
    # Daha once reddedilmisse o kayit silinir: hesap artik onayli.
    company.rejected_at = None
    company.rejected_by_id = None
    company.rejection_reason = None
    db.session.commit()
    flash(f"{company.company_name} onaylandı. Artık aday havuzuna erişebilir.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/kurumlar/<int:company_id>/reddet", methods=["POST"])
@login_required
@role_required("admin")
def admin_reject_company(company_id):
    """Basvuruyu reddeder.

    Hesap SILINMEZ, "reddedildi" olarak isaretlenir. Boylece kurum giris
    denediginde sonsuza kadar "onay bekleniyor" gormek yerine net bir
    cevap alir, karar kayda geçer ve gerekirse yeniden degerlendirilir.
    """
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    sebep = request.form.get("reason", "").strip()[:500]

    company.is_approved = False
    company.rejected_at = datetime.now()
    company.rejected_by_id = current_user.id
    company.rejection_reason = sebep or None
    db.session.commit()

    guvenlik_log.info("Kurum basvurusu reddedildi: %s, yonetici=%s",
                      company.email, current_user.email)
    flash(f"{company.company_name} başvurusu reddedildi.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/kurumlar/<int:company_id>/yeniden", methods=["POST"])
@login_required
@role_required("admin")
def admin_reconsider_company(company_id):
    """Reddedilen basvuruyu tekrar 'bekliyor' durumuna alir."""
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    company.rejected_at = None
    company.rejected_by_id = None
    company.rejection_reason = None
    db.session.commit()
    flash(f"{company.company_name} yeniden değerlendirmeye alındı.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/kurumlar/<int:company_id>/iptal", methods=["POST"])
@login_required
@role_required("admin")
def admin_revoke_company(company_id):
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    company.is_approved = False
    # approved_at/approved_by MEVCUT onayi tarif eder; erisim kalkinca
    # temizlenir. Tam bir gecmis (her onay/iptal hareketi) istenirse ayri
    # bir tablo gerekir; bu iki kolon yalnizca son durumu tutar.
    company.approved_at = None
    company.approved_by_id = None
    db.session.commit()
    flash(f"{company.company_name} erişimi kaldırıldı.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin")
@login_required
@role_required("admin")
def admin_overview():
    """Koordinatorun giris ekrani: platformun tek bakista ozeti."""
    students = User.query.filter_by(role="student").all()
    companies = User.query.filter_by(role="company").all()
    departments = Department.query.order_by(Department.name).all()

    ozet = {
        "ogrenci": len(students),
        "eksiksiz": sum(1 for s in students if s.is_profile_complete()),
        "transkript": sum(1 for s in students if s.transcript_filename),
        "dogrulanmis": sum(1 for s in students if s.transcript_verified),
        "kurum_onayli": sum(1 for c in companies if c.is_approved),
        "kurum_bekleyen": sum(1 for c in companies if c.basvuru_durumu == "bekliyor"),
        "kurum_reddedilen": sum(1 for c in companies if c.basvuru_durumu == "reddedildi"),
    }

    # Bolum dagilimi: hangi bolumde kac ogrenci, en kalabaliktan baslayarak
    dagilim = sorted(
        ((d.name, sum(1 for s in students if s.department == d.name)) for d in departments),
        key=lambda x: -x[1],
    )
    # Listede olmayan bir bolume kayitli ogrenciler (eski/bozuk veri)
    bilinen = {d.name for d in departments}
    baska = sum(1 for s in students if s.department and s.department not in bilinen)

    return render_template(
        "admin_overview.html", ozet=ozet, dagilim=dagilim, baska=baska,
        en_cok=max((a for _, a in dagilim), default=0),
    )


@app.route("/admin/ogrenciler")
@login_required
@role_required("admin")
def admin_students():
    """Ogrenci listesi.

    Koordinatorun ogrencileri gorebilmesi gerekir: destek istegi geldiginde
    kisiyi bulmak, profili eksik olanlari tespit edip hatirlatma yapmak ve
    sahte kayitlari temizlemek icin.
    """
    q = request.args.get("q", "").strip()
    durum = request.args.get("durum", "")

    query = User.query.filter_by(role="student")
    if q:
        like = f"%{q}%"
        query = query.filter(db.or_(User.full_name.ilike(like), User.email.ilike(like)))

    students = query.all()

    if durum == "eksik":
        students = [s for s in students if not s.is_profile_complete()]
    elif durum == "transkriptsiz":
        students = [s for s in students if not s.transcript_filename]
    elif durum == "dogrulanmamis":
        students = [s for s in students if s.transcript_filename and not s.transcript_verified]

    students.sort(key=lambda s: (s.full_name or "").casefold())

    return render_template(
        "admin_students.html", students=students, q=q, durum=durum,
        toplam=User.query.filter_by(role="student").count(),
    )


@app.route("/admin/ogrenciler/<int:student_id>/transkript-dogrula", methods=["POST"])
@login_required
@role_required("admin")
def admin_verify_transcript(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    if not student.transcript_filename:
        flash("Bu öğrencinin yüklenmiş transkripti yok.", "error")
        return redirect(url_for("admin_students"))

    student.transcript_verified = True
    student.transcript_verified_at = datetime.now()
    student.transcript_verified_by_id = current_user.id
    db.session.commit()
    guvenlik_log.info("Transkript dogrulandi: ogrenci=%s, yonetici=%s",
                      student.email, current_user.email)
    flash(f"{student.full_name} — transkript doğrulandı.", "success")
    return redirect(request.referrer or url_for("admin_students"))


@app.route("/admin/ogrenciler/<int:student_id>/transkript-iptal", methods=["POST"])
@login_required
@role_required("admin")
def admin_unverify_transcript(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    student.transcript_verified = False
    student.transcript_verified_at = None
    student.transcript_verified_by_id = None
    db.session.commit()
    guvenlik_log.info("Transkript dogrulamasi kaldirildi: ogrenci=%s, yonetici=%s",
                      student.email, current_user.email)
    flash(f"{student.full_name} — transkript doğrulaması kaldırıldı.", "success")
    return redirect(request.referrer or url_for("admin_students"))


@app.route("/admin/kullanici/<int:user_id>/sil", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_user(user_id):
    """Hesabi ve ona bagli her seyi siler. GERI ALINAMAZ.

    Veritabani kaydi cascade ile gider (egitim/deneyim/sertifika/proje), ama
    diskteki dosyalar otomatik silinmez -- onlari elle kaldirmak gerekir,
    aksi halde silinen ogrencinin transkripti sunucuda kalirdi.
    """
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Kendi hesabınızı silemezsiniz.", "error")
        return redirect(url_for("admin_students"))
    if user.role == "admin":
        flash("Yönetici hesapları buradan silinemez.", "error")
        return redirect(url_for("admin_students"))

    # Diskteki dosyalari temizle
    for klasor, dosya in ((TRANSCRIPT_FOLDER, user.transcript_filename),
                          (PHOTO_FOLDER, user.photo_filename)):
        if dosya:
            try:
                os.remove(os.path.join(klasor, dosya))
            except OSError:
                pass        # dosya zaten yoksa sorun degil

    ad = user.full_name or user.company_name or user.email
    eposta, rol = user.email, user.role
    db.session.delete(user)
    db.session.commit()

    guvenlik_log.warning("Hesap silindi: %s (%s), silen yonetici=%s",
                         eposta, rol, current_user.email)
    flash(f"{ad} hesabı ve tüm kayıtları silindi.", "success")
    return redirect(url_for("admin_students") if rol == "student"
                    else url_for("admin_companies"))


@app.route("/admin/bolumler", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_departments():
    """Bolum listesi yonetimi.

    Bolumler onceden yalnizca seed_departments() icinde sabitti; yeni bolum
    eklemek kod degisikligi gerektiriyordu. Burasi koordinatorun kendi
    ekleyip silebilmesi icin.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bölüm adı boş olamaz.", "error")
        elif Department.query.filter_by(name=name).first():
            flash(f"'{name}' zaten listede.", "error")
        else:
            db.session.add(Department(name=name))
            db.session.commit()
            flash(f"'{name}' bölümü eklendi.", "success")
        return redirect(url_for("admin_departments"))

    departments = Department.query.order_by(Department.name).all()
    # Her bolumde kac ogrenci var: silmeden once uyarmak icin
    counts = {
        d.name: User.query.filter_by(role="student", department=d.name).count()
        for d in departments
    }
    return render_template(
        "admin_departments.html", departments=departments, counts=counts
    )


@app.route("/admin/bolumler/<int:department_id>/sil", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_department(department_id):
    department = Department.query.get_or_404(department_id)

    # Bolum, ogrenci kayitlarinda metin olarak tutuluyor (iliski degil).
    # Silinirse o ogrencilerin bolumu listede olmayan bir metne doner ve
    # filtrelerde kaybolurlar; bu yuzden doluyken silinmesine izin yok.
    in_use = User.query.filter_by(role="student", department=department.name).count()
    if in_use:
        flash(
            f"'{department.name}' silinemez: {in_use} öğrenci bu bölüme kayıtlı. "
            "Önce o öğrencilerin bölümünü değiştirin.",
            "error",
        )
    else:
        db.session.delete(department)
        db.session.commit()
        flash(f"'{department.name}' bölümü silindi.", "success")

    return redirect(url_for("admin_departments"))


# ---------- Çıkış ----------

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


# ---------- API katmani ----------
# JSON'u girintili bas. Varsayilan sikistirilmis bicim tek satirdir ve
# tarayicida okunaksiz bir metin duvari olarak gorunur. Bu API insan
# tarafindan da acilacagi icin (uc noktayi tarayiciya yazip bakmak) okunurluk
# birkac yuz baytlik buyumeye deger.
app.json.compact = False


# Blueprint, Flask'ta rotalari ortak bir onek ve ortak davranis altinda
# grupladan yapidir -- Laravel'deki routes/api.php dosyasinin karsiligi.
# Ayri bir dosyada (api.py) durur: sayfalar insana, API makineye konusur.
app.register_blueprint(api_blueprint)

# API acik bir veri kaynagi; sayfalardan daha genis bir sinir yeterli ama
# sinirsiz olmamali. Bir betik saniyede yuzlerce istek atarsa ucretsiz
# katmanin gunluk CPU butcesi tukenir ve SITE TAMAMEN durur.
limiter.limit("120 per minute; 2000 per hour")(api_blueprint)

# CSRF korumasi yalnizca durum degistiren metotlar icindir ve cerez tabanli
# oturuma dayanir. API salt-okunur ve cerezsiz oldugu icin konu disi; yine de
# acikca muaf tutuluyor ki ileride POST eklenirse bilincli bir karar olsun.
csrf.exempt(api_blueprint)


def create_app():
    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["PHOTO_FOLDER"], exist_ok=True)
        db.create_all()
        seed_departments()
    return app


if __name__ == "__main__":
    create_app()
    # Debug modu disa acik bir adreste ASLA acik olmamali: hata aninda
    # tarayicida interaktif Python konsolu acilir, yani sunucuda kod
    # calistirilabilir. Yerel gelistirmede varsayilan olarak acik kalir;
    # tunel/sunucu icin FLASK_DEBUG=0 verilir.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    port = int(os.environ.get("PORT", 5000))

    if not debug and app.config["SECRET_KEY"] == "dev-secret-anahtari-degistir":
        raise SystemExit(
            "SECRET_KEY ayarlanmamis. Disa acik calistirmadan once ortam "
            "degiskeni olarak guclu ve rastgele bir deger verin."
        )

    app.run(debug=debug, host="0.0.0.0", port=port)
    
@app.cli.command("approve-company")
def approve_company():
    """Onay bekleyen kurumları listeler ve onaylama imkanı verir."""
    pending = User.query.filter_by(role="company", is_approved=False).all()
    if not pending:
        print("Onay bekleyen kurum bulunmuyor.")
        return

    print("\n--- Onay Bekleyen Kurumlar ---")
    for c in pending:
        print(f"ID: {c.id} | Şirket: {c.company_name} | Yetkili: {c.contact_person} | E-posta: {c.email}")
    
    comp_id = input("\nOnaylamak istediğiniz Kurum ID'sini girin (Tümünü onaylamak için 'all'): ").strip()
    if comp_id == "all":
        for c in pending:
            c.is_approved = True
        db.session.commit()
        print("Tüm kurumlar onaylandı.")
    elif comp_id.isdigit():
        target = User.query.get(int(comp_id))
        if target and target.role == "company":
            target.is_approved = True
            db.session.commit()
            print(f"{target.company_name} başarıyla onaylandı.")
        else:
            print("Geçersiz kurum ID.")


@app.cli.command("create-admin")
def create_admin():
    """Yonetici (kampus koordinatoru) hesabi olusturur.

    Yonetici hesabi tarayicidan acilamaz; tek yol bu komuttur.
    Kullanim:  flask --app app create-admin
    """
    import getpass

    email = input("Yonetici e-postasi: ").strip().lower()
    if not email:
        print("E-posta bos olamaz.")
        return

    if User.query.filter_by(email=email).first():
        print(f"'{email}' ile zaten bir hesap var.")
        return

    full_name = input("Ad soyad: ").strip() or "Kampus Koordinatoru"

    password = getpass.getpass("Sifre (en az 6 karakter): ")
    if len(password) < 6:
        print("Sifre en az 6 karakter olmali.")
        return
    if password != getpass.getpass("Sifre (tekrar): "):
        print("Sifreler eslesmiyor.")
        return

    db.session.add(User(
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
        full_name=full_name,
    ))
    db.session.commit()
    print(f"Yonetici olusturuldu: {email}")
    print("Giris: /admin/giris")


@app.cli.command("seed-demo")
def seed_demo():
    """Tanitim icin UYDURMA ogrenci verisi olusturur.

    Gercek kisisel veri iceren veritabani sunucuya hic gonderilmez
    (.dockerignore); dagitim bos bir veritabaniyla acilir. Bu komut,
    aray�z� dolu gostermek icin tamamen kurgusal kayitlar uretir.

    Kullanim:  flask --app app seed-demo
    """
    import random
    from datetime import timedelta

    if User.query.filter(User.email.like("%@ornek.edu.tr")).first():
        print("Demo verisi zaten var. Once temizlemek icin: flask --app app clear-demo")
        return

    random.seed(42)   # her calistirmada ayni sonuc

    adlar = ["Elif", "Yusuf", "Zeynep", "Mert", "Ayse", "Burak", "Deniz", "Emre",
             "Selin", "Kaan", "Irem", "Ozan", "Ece", "Baris", "Nehir", "Tolga",
             "Melis", "Arda", "Sude", "Efe", "Derya", "Cem", "Buse", "Hakan",
             "Pinar", "Onur", "Gizem", "Serkan"]
    soyadlar = ["Yilmaz", "Demir", "Kaya", "Celik", "Sahin", "Aydin", "Ozturk",
                "Arslan", "Dogan", "Kilic", "Aslan", "Cetin", "Kara", "Koc"]
    okullar = ["Kirikkale Universitesi", "Yalova Universitesi", "Ege Universitesi",
               "Anadolu Universitesi", "Karadeniz Teknik Universitesi"]
    sirketler = ["Teknoloji A.S.", "Veri Sistemleri", "Fiber Net", "Mavi Yazilim",
                 "Kuzey Telekom", "Akilli Sebeke"]
    pozisyonlar = ["Stajyer Yazilim Gelistirici", "Ag Teknisyeni Stajyeri",
                   "Veri Analisti Stajyeri", "Saha Destek Stajyeri"]
    sertifikalar = [("Ag Temelleri", "Cisco"), ("Bulut Temelleri", "AWS"),
                    ("Veri Analizi", "Google"), ("Siber Guvenlik 101", "TUBITAK")]
    projeler = [("Kampus Ag Simulasyonu", "Python, NS-3"),
                ("Fiber Kesinti Haritasi", "Flask, Leaflet"),
                ("Ogrenci Yoklama Sistemi", "Django, SQLite"),
                ("Sensor Veri Panosu", "Python, Grafana")]

    bolumler = [d.name for d in Department.query.all()] or ["Fiber Teknolojisi"]
    sifre = generate_password_hash("demo1234")
    bugun = datetime.now()

    # Paylasilan ornek transkript (gercek bir belge degil)
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    os.makedirs(TRANSCRIPT_FOLDER, exist_ok=True)
    ornek_transkript = "ornek_transkript.pdf"
    yol = os.path.join(TRANSCRIPT_FOLDER, ornek_transkript)
    if not os.path.exists(yol):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(yol)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(70, 760, "ORNEK TRANSKRIPT")
        c.setFont("Helvetica", 11)
        c.drawString(70, 730, "Bu belge tanitim amaciyla uretilmistir.")
        c.drawString(70, 712, "Gercek bir ogrenciye ait degildir.")
        c.save()

    olusan = 0
    for i in range(28):
        ad = f"{adlar[i % len(adlar)]} {random.choice(soyadlar)}"
        eposta = f"ogrenci{i + 1:02d}@ornek.edu.tr"

        # Doluluk cesitliligi: bazilari eksik profil, bazilari eksiksiz
        seviye = i % 4          # 0=cok eksik, 3=eksiksiz
        ogr = User(
            email=eposta,
            password_hash=sifre,
            role="student",
            full_name=ad,
            department=random.choice(bolumler),
            phone=f"05{random.randint(10, 59)}{random.randint(1000000, 9999999)}",
            summary=("Kariyerine aglar ve veri alaninda devam etmek isteyen "
                     "son sinif ogrencisi.") if seviye >= 1 else None,
            skills=", ".join(random.sample(
                ["Python", "SQL", "Linux", "Ag Yonetimi", "Excel", "Git",
                 "Fiber Optik", "Ingilizce"], k=random.randint(3, 5))
            ) if seviye >= 1 else None,
            transcript_filename=ornek_transkript if seviye >= 2 else None,
            created_at=bugun - timedelta(days=random.randint(1, 300)),
        )
        db.session.add(ogr)
        db.session.flush()

        bitis = random.randint(2023, 2027)
        db.session.add(Education(
            student_id=ogr.id, degree_type="Lisans",
            school=random.choice(okullar), department=ogr.department,
            gpa=f"{random.uniform(2.1, 3.95):.2f}",
            start_year=str(bitis - 4), end_year=str(bitis),
        ))
        if seviye >= 2:
            sirket = random.choice(sirketler)
            db.session.add(Experience(
                student_id=ogr.id, company=sirket,
                position=random.choice(pozisyonlar),
                start_date="Haz 2025", end_date="Agu 2025",
                description=f"{sirket} bunyesinde yaz stajini tamamladi.",
            ))
        if seviye >= 3:
            sad, kurum = random.choice(sertifikalar)
            # Demo verisinde sertifikalarin bir kismi dogrulanabilir olsun ki
            # "doğrula" baglantisinin ve belge no'nun nasil gorundugu denenebilsin.
            kod = f"{kurum[:3].upper()}-{random.randint(10000, 99999)}"
            db.session.add(Certificate(
                student_id=ogr.id, name=sad, institution=kurum, date="2025",
                credential_id=kod,
                credential_url=(f"https://ornek-dogrulama.test/belge/{kod}"
                                if random.random() < 0.6 else None)))
            pad, tek = random.choice(projeler)
            db.session.add(Project(
                student_id=ogr.id, title=pad, tech_stack=tek,
                description="Donem projesi kapsaminda gelistirildi."))
        olusan += 1

    # Tanitim icin onayli bir kurum hesabi
    if not User.query.filter_by(email="demo@ornek.com").first():
        db.session.add(User(
            email="demo@ornek.com", password_hash=sifre, role="company",
            company_name="Ornek Kurum A.S.", contact_person="Demo Yetkili",
            is_approved=True, created_at=bugun,
        ))

    # Onay ekraninda gosterilecek, onay BEKLEYEN bir kurum
    if not User.query.filter_by(email="bekleyen@ornek.com").first():
        db.session.add(User(
            email="bekleyen@ornek.com", password_hash=sifre, role="company",
            company_name="Bekleyen Kurum Ltd.", contact_person="Aday Yetkili",
            is_approved=False, created_at=bugun,
        ))

    db.session.commit()
    print(f"{olusan} uydurma ogrenci olusturuldu.")
    print("  Kurum (onayli) : demo@ornek.com / demo1234")
    print("  Kurum (bekleyen): bekleyen@ornek.com")
    print("  Ogrenci         : ogrenci01@ornek.edu.tr / demo1234")
    print("\nYonetici hesabi ayrica olusturulmali: flask --app app create-admin")


@app.cli.command("clear-demo")
def clear_demo():
    """seed-demo ile olusturulan uydurma kayitlari siler."""
    demo = User.query.filter(
        db.or_(User.email.like("%@ornek.edu.tr"), User.email.like("%@ornek.com"))
    ).all()
    for u in demo:
        db.session.delete(u)      # cascade ile CV kayitlari da gider
    db.session.commit()
    print(f"{len(demo)} demo kaydi silindi.")
