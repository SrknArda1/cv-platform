"""Hiz siniri: F5'e basili tutma ve toplu istekler.

conftest limiter'i kapali tutar (yoksa diger testler sinira takilirdi); bu
dosyadaki testler kendi fixture'lariyla acar ve sayaclari sifirlar.
"""
import pytest

from app import limiter
from conftest import oturum_ac
from models import db, User

SAYFA_SINIRI = 120
GIRIS_SINIRI = 60


@pytest.fixture
def sinir_acik(uygulama):
    limiter.enabled = True
    limiter.reset()
    yield uygulama
    limiter.reset()
    limiter.enabled = False


def _durumlar(istek, adet):
    return [istek().status_code for _ in range(adet)]


def test_sayfa_sinira_kadar_acilir_sonra_429(sinir_acik):
    istemci = sinir_acik.test_client()

    assert set(_durumlar(lambda: istemci.get("/"), SAYFA_SINIRI)) == {200}
    assert istemci.get("/").status_code == 429


def test_429_tasarimli_html_sayfasi_doner(sinir_acik):
    istemci = sinir_acik.test_client()
    _durumlar(lambda: istemci.get("/"), SAYFA_SINIRI)

    yanit = istemci.get("/")

    assert "text/html" in yanit.content_type
    assert "Çok fazla istek" in yanit.get_data(as_text=True)


def test_sinir_ip_basina_uygulanir(sinir_acik):
    """Birinin F5'i baska bir kullaniciyi engellememeli."""
    saldirgan = sinir_acik.test_client()
    _durumlar(lambda: saldirgan.get("/"), SAYFA_SINIRI + 1)

    baska = sinir_acik.test_client()
    yanit = baska.get("/", environ_base={"REMOTE_ADDR": "10.0.0.2"})

    assert yanit.status_code == 200


def test_statik_dosyalar_sayilmaz(sinir_acik):
    istemci = sinir_acik.test_client()

    assert set(_durumlar(lambda: istemci.get("/static/style.css"),
                         SAYFA_SINIRI + 10)) == {200}
    assert istemci.get("/").status_code == 200


def test_fotograflar_sayfa_sinirini_tuketmez(sinir_acik):
    """Aday havuzunda sayfa basina 25 fotograf var: taban sinira dahil olsaydi
    kurum birkac sayfa gezince engellenirdi."""
    with sinir_acik.app_context():
        kurum = User(email="k@test.local", password_hash="x", role="company",
                     company_name="Kurum", is_approved=True)
        db.session.add(kurum)
        db.session.commit()
        kurum_id = kurum.id
    istemci = oturum_ac(sinir_acik.test_client(), kurum_id)

    durumlar = _durumlar(lambda: istemci.get("/uploads/photos/yok.png"),
                         SAYFA_SINIRI + 10)

    assert 429 not in durumlar
    # Girisli kurum ana sayfadan panele yonlenir (302); onemli olan engellenmemesi.
    assert istemci.get("/").status_code != 429


def test_giris_denemesi_kendi_sinirinda_kalir(sinir_acik):
    """Taban sinir, sifre denemesine karsi olan daha siki siniri gevsetmemeli."""
    istemci = sinir_acik.test_client()
    veri = {"email": "yok@test.local", "password": "yanlis"}

    durumlar = _durumlar(lambda: istemci.post("/company/login", data=veri),
                         GIRIS_SINIRI)

    assert 429 not in durumlar
    assert istemci.post("/company/login", data=veri).status_code == 429


def test_api_kendi_sinirini_ve_json_hatasini_korur(sinir_acik):
    istemci = sinir_acik.test_client()

    assert set(_durumlar(lambda: istemci.get("/api/v1/ozet"), 120)) == {200}
    yanit = istemci.get("/api/v1/ozet")

    assert yanit.status_code == 429
    assert yanit.is_json
