"""Testler icin ortak kurulum.

ONEMLI: ortam degiskenleri app ice aktarilmadan ONCE ayarlanmali. app.py
DATA_DIR'i modul seviyesinde okuyor; import'tan sonra degistirmek gec kalir
ve testler GERCEK veritabanina baglanir. conftest.py pytest tarafindan her
seyden once yuklendigi icin dogru yer burasi.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KOK))

# Gercek veritabanina ASLA dokunulmasin diye gecici bir klasor.
_GECICI = tempfile.mkdtemp(prefix="kariyer-test-")
os.environ["DATA_DIR"] = _GECICI
os.environ["SECRET_KEY"] = "test-anahtari"
os.environ["API_ANAHTARI"] = "test-api-anahtari"
os.environ["FLASK_DEBUG"] = "1"

from app import app as _uygulama, create_app, limiter, seed_departments  # noqa: E402
from models import (db, User, Education, Experience, Certificate,  # noqa: E402
                    Project, Department, Message)
from werkzeug.security import generate_password_hash  # noqa: E402

API_ANAHTARI = "test-api-anahtari"

_uygulama.config["TESTING"] = True
_uygulama.config["WTF_CSRF_ENABLED"] = False
limiter.enabled = False
create_app()


def pytest_sessionfinish(session, exitstatus):
    """Test bitince gecici veritabanini sil."""
    shutil.rmtree(_GECICI, ignore_errors=True)


@pytest.fixture
def uygulama():
    """Her test icin bos ve taze bir veritabani.

    DIKKAT -- uygulama baglami testin tamami boyunca ACIK TUTULMAZ.
    Flask-Login giris yapmis kullaniciyi `g` uzerinde onbellege alir ve `g`
    uygulama baglamina baglidir. Baglam acik kalirsa test istemcisinin tum
    istekleri ayni `g`'yi paylasir; oturumu degistirseniz bile ikinci istek
    birincinin kullanicisini gorur ve yetki testleri YANLIS YERE gecer.
    Model sorgusu gereken testler kendi `with uygulama.app_context():`
    blogunu acar.
    """
    with _uygulama.app_context():
        db.drop_all()
        db.create_all()
        seed_departments()
    yield _uygulama


@pytest.fixture
def istemci(uygulama):
    return uygulama.test_client()


@pytest.fixture
def bolumler(uygulama):
    with uygulama.app_context():
        return [d.name for d in Department.query.order_by(Department.id).all()]


# --- Ornek veri ---------------------------------------------------------
# Kisisel veri sizintisi testleri bu sabitleri arar: API yanitlarinin
# hicbirinde gorunmemeleri gerekir.

AD = "Ayse Yilmaz Demirkan"
EPOSTA = "ayse.demirkan@ornek-universite.edu.tr"
TELEFON = "05551234567"
OZET = "Cok gizli kisisel ozet metni."
TRANSKRIPT = "transcript_gizli_dosya.pdf"
FOTO = "photo_gizli.png"
KURUM_ADI = "Ornek Teknoloji A.S."


@pytest.fixture
def veri(uygulama, bolumler):
    """Iki ogrenci, iki kurum, bir yonetici ve bagli CV kayitlari.

    Birinci ogrenci DOLU (profil %100), ikincisi bos -- filtre ve dagilim
    testleri ikisinin farkina dayaniyor. Donen deger yalin id sozlugudur;
    model nesnesi dondurulse baglam kapandiginda kullanilamaz hale gelirdi.
    """
    with uygulama.app_context():
        return _veri_olustur(bolumler)


def _veri_olustur(bolumler):
    sifre = generate_password_hash("sifre123")

    dolu = User(email=EPOSTA, password_hash=sifre, role="student",
                full_name=AD, department=bolumler[0], phone=TELEFON,
                summary=OZET, skills="Python, Ag Guvenligi, C#",
                transcript_filename=TRANSKRIPT, photo_filename=FOTO,
                transcript_verified=True)
    bos = User(email="bos@test.local", password_hash=sifre, role="student",
               full_name="Bos Profil", department=bolumler[1],
               skills="Python, SQL")
    kurum = User(email="kurum@test.local", password_hash=sifre, role="company",
                 company_name=KURUM_ADI, is_approved=True)
    bekleyen = User(email="bekleyen@test.local", password_hash=sifre,
                    role="company", company_name="Bekleyen A.S.",
                    is_approved=False)
    yonetici = User(email="admin@test.local", password_hash=sifre,
                    role="admin", full_name="Koordinator")
    db.session.add_all([dolu, bos, kurum, bekleyen, yonetici])
    db.session.flush()

    db.session.add(Education(student_id=dolu.id, school="Yalova Universitesi",
                             degree_type="Lisans", gpa="3,40",
                             start_year="2021", end_year="2025"))
    db.session.add(Experience(student_id=dolu.id, company="Ornek A.S.",
                              position="Stajyer", start_date="Haz 2025",
                              end_date="Agu 2025", description="Yaz stajı."))
    db.session.add(Certificate(student_id=dolu.id, name="AWS Cloud Practitioner",
                               institution="Amazon", date="2024",
                               credential_id="AWS-PSA-12345",
                               credential_url="https://www.credly.com/badges/abc"))
    db.session.add(Certificate(student_id=dolu.id, name="Ag Temelleri",
                               institution="Cisco", date="2023"))
    db.session.add(Project(student_id=dolu.id, title="Donem Projesi",
                           tech_stack="Python, NS-3"))
    db.session.add(Message(sender_id=kurum.id, recipient_id=dolu.id,
                           body="Merhaba, profilinizi inceledik."))
    db.session.commit()

    return {
        "dolu": dolu.id, "bos": bos.id, "kurum": kurum.id,
        "bekleyen": bekleyen.id, "yonetici": yonetici.id,
    }


def oturum_ac(istemci, kullanici_id):
    """Flask-Login oturumunu dogrudan kurar; giris formundan gecmeye gerek yok."""
    with istemci.session_transaction() as oturum:
        oturum["_user_id"] = str(kullanici_id)
        oturum["_fresh"] = True
    return istemci
