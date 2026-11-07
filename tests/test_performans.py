"""N+1 sorgu korumasi ve CLI komutlarinin ciktisi.

Sure olcmek testi makineye bagimli yapar; bu yuzden sorgu SAYISI denetlenir:
ogrenci sayisi artinca sorgu sayisi artiyorsa N+1 geri gelmis demektir.
"""
import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from conftest import oturum_ac
from models import db, User, Education, Experience, Certificate, Project


def _ogrenci_ekle(adet, baslangic=0):
    for i in range(baslangic, baslangic + adet):
        ogrenci = User(email=f"o{i}@test.local", password_hash="x", role="student",
                       full_name=f"Ogrenci {i}", department="Fiber Teknolojisi",
                       skills="Python")
        db.session.add(ogrenci)
        db.session.flush()
        db.session.add_all([
            Education(student_id=ogrenci.id, school="Okul", gpa="3,10", end_year="2025"),
            Experience(student_id=ogrenci.id, company="Firma"),
            Certificate(student_id=ogrenci.id, name="Sertifika"),
            Project(student_id=ogrenci.id, title="Proje"),
        ])
    db.session.commit()


def _sorgu_say(istemci, adres):
    sayac = []

    def say(*_):
        sayac.append(1)

    event.listen(Engine, "before_cursor_execute", say)
    try:
        yanit = istemci.get(adres)
    finally:
        event.remove(Engine, "before_cursor_execute", say)
    assert yanit.status_code == 200
    return len(sayac)


@pytest.mark.parametrize("rol,adres", [
    ("company", "/company/dashboard"),
    ("company", "/company/dashboard?sort=gpa"),
    ("company", "/company/dashboard?min_completion=50"),
    ("admin", "/admin"),
    ("admin", "/admin/ogrenciler"),
])
def test_sorgu_sayisi_ogrenci_sayisiyla_artmaz(uygulama, rol, adres):
    with uygulama.app_context():
        kullanici = User(email="k@test.local", password_hash="x", role=rol,
                         company_name="Kurum", full_name="Yonetici", is_approved=True)
        db.session.add(kullanici)
        db.session.commit()
        kullanici_id = kullanici.id
        _ogrenci_ekle(3)

    istemci = oturum_ac(uygulama.test_client(), kullanici_id)
    az = _sorgu_say(istemci, adres)

    with uygulama.app_context():
        _ogrenci_ekle(12, baslangic=3)

    assert _sorgu_say(istemci, adres) == az


def test_api_yalnizca_okuma_yapar(uygulama):
    """API'nin CSRF muafiyetine ihtiyaci yok, cunku durum degistiren metodu yok."""
    for kural in uygulama.url_map.iter_rules():
        if kural.endpoint.startswith("api."):
            assert kural.methods <= {"GET", "HEAD", "OPTIONS"}, kural.rule


def test_seed_demo_ve_clear_demo_cikti_verir(uygulama):
    """print yerine click.echo: komutlarin ciktisi kullaniciya ulasmali."""
    calistir = uygulama.test_cli_runner().invoke

    sonuc = calistir(args=["seed-demo"])
    assert sonuc.exit_code == 0
    assert "uydurma ogrenci olusturuldu" in sonuc.output

    assert "Demo verisi zaten var" in calistir(args=["seed-demo"]).output

    sonuc = calistir(args=["clear-demo"])
    assert sonuc.exit_code == 0
    assert "demo kaydi silindi" in sonuc.output
