"""Duman testi: her rol icin ana sayfalar aciliyor mu, yetkiler tutuyor mu.

Ayrintiya girmez -- amaci bir degisikligin sistemin tamamini kirip kirmadigini
hizlica soylemek.
"""
import pytest

from conftest import oturum_ac

ACIK_SAYFALAR = ["/", "/kvkk", "/api", "/student/login", "/company/login",
                 "/admin/giris", "/student/register", "/company/register"]
OGRENCI_SAYFALARI = ["/student/dashboard", "/student/cv", "/student/preview",
                     "/mesajlar"]
KURUM_SAYFALARI = ["/company/dashboard", "/company/profil", "/mesajlar"]
YONETICI_SAYFALARI = ["/admin", "/admin/kurumlar", "/admin/ogrenciler",
                      "/admin/bolumler"]
KORUMALI = ["/student/dashboard", "/company/dashboard", "/admin",
            "/student/cv", "/mesajlar", "/uploads/photos/x.png"]


@pytest.mark.parametrize("yol", ACIK_SAYFALAR)
def test_acik_sayfalar(istemci, veri, yol):
    assert istemci.get(yol).status_code == 200


@pytest.mark.parametrize("yol", KORUMALI)
def test_oturumsuz_erisim_yonlendiriliyor(istemci, veri, yol):
    assert istemci.get(yol).status_code == 302


@pytest.mark.parametrize("yol", OGRENCI_SAYFALARI)
def test_ogrenci_sayfalari(istemci, veri, yol):
    oturum_ac(istemci, veri["dolu"])
    assert istemci.get(yol).status_code == 200


@pytest.mark.parametrize("yol", KURUM_SAYFALARI)
def test_kurum_sayfalari(istemci, veri, yol):
    oturum_ac(istemci, veri["kurum"])
    assert istemci.get(yol).status_code == 200


@pytest.mark.parametrize("yol", YONETICI_SAYFALARI)
def test_yonetici_sayfalari(istemci, veri, yol):
    oturum_ac(istemci, veri["yonetici"])
    assert istemci.get(yol).status_code == 200


def test_roller_birbirinin_sayfasina_giremiyor(istemci, veri):
    oturum_ac(istemci, veri["dolu"])
    assert istemci.get("/company/dashboard").status_code == 403
    oturum_ac(istemci, veri["kurum"])
    assert istemci.get("/student/dashboard").status_code == 403


def test_kurum_aday_cvsini_ve_pdfini_gorebiliyor(istemci, veri):
    """cv_detail.html ogrenci onizlemesiyle PAYLASILIYOR -- iki taraf da calismali."""
    oturum_ac(istemci, veri["kurum"])
    sayfa = istemci.get(f"/company/student/{veri['dolu']}")
    assert sayfa.status_code == 200
    assert "Belge no AWS-PSA-12345" in sayfa.get_data(as_text=True)

    pdf = istemci.get(f"/company/student/{veri['dolu']}/pdf")
    assert pdf.status_code == 200
    assert pdf.get_data()[:4] == b"%PDF"


# ---------- Hata sayfalari ----------

def test_site_404u_html_kaliyor(istemci, veri):
    cevap = istemci.get("/boyle-bir-sayfa-yok")
    assert cevap.status_code == 404
    assert "Sayfa bulunamadı" in cevap.get_data(as_text=True)


def test_api_altinda_404_json(istemci, veri):
    cevap = istemci.get("/api/v1/olmayan")
    assert cevap.status_code == 404
    assert "application/json" in cevap.headers["Content-Type"]


def test_api_belge_sayfasi_html_kaliyor(istemci, veri):
    """/api bir HTML sayfasi; JSON denetimi yalnizca /api/v1 icin gecerli."""
    cevap = istemci.get("/api/olmayan-sayfa")
    assert cevap.status_code == 404
    assert "text/html" in cevap.headers["Content-Type"]


# ---------- Kayit dogrulamasi ----------

@pytest.mark.parametrize("alanlar,beklenen_mesaj", [
    ({"full_name": "T", "email": "bozuk@gmail", "password": "abc123",
      "password2": "abc123"}, "Geçerli bir e-posta"),
    ({"full_name": "T", "email": "t@ornek.com", "password": "abc123",
      "password2": "farkli"}, "eşleşmiyor"),
    ({"full_name": "T", "email": "t@ornek.com", "password": "abc",
      "password2": "abc"}, "en az 6"),
])
def test_hatali_kayit_reddediliyor(istemci, veri, alanlar, beklenen_mesaj):
    cevap = istemci.post("/student/register", data=alanlar)
    assert cevap.status_code == 400
    assert beklenen_mesaj in cevap.get_data(as_text=True)
