"""/api/v1 REST katmani."""
import json

import pytest

from conftest import (AD, EPOSTA, TELEFON, OZET, TRANSKRIPT, FOTO, KURUM_ADI,
                      API_ANAHTARI)

ACIK_UCLAR = ["/api/v1/", "/api/v1/ozet", "/api/v1/ogrenciler",
              "/api/v1/bolumler", "/api/v1/yetkinlikler"]

# Ogrenci kaydinda bulunmasina IZIN VERILEN alanlar. Yeni bir alan eklenirse
# bu liste de guncellenmeli -- testin amaci zaten modele eklenen bir kolonun
# sessizce disari sizmasini yakalamak.
IZINLI_ALANLAR = {
    "id", "department", "gpa", "profile_completion", "has_transcript",
    "transcript_verified", "education_count", "experience_count",
    "certificate_count", "verifiable_certificate_count", "project_count",
    "skills", "registered_at",
}


# ---------- Temel sozlesme ----------

@pytest.mark.parametrize("yol", ACIK_UCLAR)
def test_acik_uclar_json_donuyor(istemci, veri, yol):
    cevap = istemci.get(yol)
    assert cevap.status_code == 200
    assert "application/json" in cevap.headers["Content-Type"]
    assert cevap.get_json() is not None


@pytest.mark.parametrize("yol", ACIK_UCLAR)
def test_yanit_iskeleti_ayni(istemci, veri, yol):
    govde = istemci.get(yol).get_json()
    assert {"data", "meta", "links"} <= set(govde)
    assert govde["meta"]["api_version"] == "1.0"


def test_cors_ve_onbellek_basliklari(istemci, veri):
    basliklar = istemci.get("/api/v1/ozet").headers
    assert basliklar["Access-Control-Allow-Origin"] == "*"
    assert "max-age" in basliklar["Cache-Control"]


def test_json_girintili_basiliyor(istemci, veri):
    """Tarayicida gozle okunabilmesi icin; tek satir olsaydi metin duvari olurdu."""
    assert istemci.get("/api/v1/ozet").get_data(as_text=True).count("\n") > 5


# ---------- Kisisel veri sizintisi ----------
# Bu grubun hepsi tek bir soruyu soruyor: API kisisel veri sizdiriyor mu?

def _tum_yanitlar(istemci):
    metin = ""
    for yol in ACIK_UCLAR + ["/api/v1/ogrenciler?page_size=200"]:
        metin += istemci.get(yol).get_data(as_text=True)
    metin += istemci.get("/api/v1/ozet/detay",
                         headers={"X-API-Key": API_ANAHTARI}).get_data(as_text=True)
    return metin


@pytest.mark.parametrize("etiket,gizli", [
    ("ad soyad", AD),
    ("e-posta", EPOSTA),
    ("telefon", TELEFON),
    ("kisisel ozet", OZET),
    ("transkript dosya adi", TRANSKRIPT),
    ("fotograf dosya adi", FOTO),
    ("kurum adi", KURUM_ADI),
])
def test_kisisel_veri_hicbir_yanitta_gecmiyor(istemci, veri, etiket, gizli):
    assert gizli not in _tum_yanitlar(istemci), f"{etiket} sizdi"


def test_sifre_hashi_sizmaz(istemci, veri):
    assert "password" not in _tum_yanitlar(istemci)


def test_ogrenci_kaydi_yalnizca_izinli_alanlari_tasir(istemci, veri):
    kayitlar = istemci.get("/api/v1/ogrenciler").get_json()["data"]
    alanlar = set()
    for kayit in kayitlar:
        alanlar |= set(kayit)
    assert alanlar <= IZINLI_ALANLAR, f"beklenmeyen alan: {alanlar - IZINLI_ALANLAR}"


# ---------- Veri dogrulugu ----------

def test_ozet_sayimlari(istemci, veri):
    govde = istemci.get("/api/v1/ozet").get_json()["data"]
    assert govde["students"]["total"] == 2
    assert govde["students"]["with_transcript"] == 1
    assert govde["students"]["transcript_verified"] == 1
    assert govde["companies"] == {"total": 2, "approved": 1, "pending": 1}
    assert govde["certificates"]["total"] == 2
    assert govde["certificates"]["verifiable"] == 1


def test_virgullu_ortalama_sayiya_cevriliyor(istemci, veri):
    """gpa alani metin; '3,40' gibi Turkce ondalik da okunabilmeli."""
    assert istemci.get("/api/v1/ozet").get_json()["data"]["students"]["average_gpa"] == 3.4


def test_tek_ogrenci_kaydi(istemci, veri):
    kayit = istemci.get(f"/api/v1/ogrenciler/{veri['dolu']}").get_json()["data"]
    assert kayit["gpa"] == 3.4
    assert kayit["certificate_count"] == 2
    assert kayit["verifiable_certificate_count"] == 1
    assert kayit["skills"] == ["Python", "Ag Guvenligi", "C#"]
    assert kayit["has_transcript"] is True


def test_yetkinlik_frekansi_azalan_sirada(istemci, veri):
    liste = istemci.get("/api/v1/yetkinlikler").get_json()["data"]
    python = [g for g in liste if g["name"].lower() == "python"]
    assert python and python[0]["student_count"] == 2
    sayilar = [g["student_count"] for g in liste]
    assert sayilar == sorted(sayilar, reverse=True)


def test_bolum_toplamlari_tutuyor(istemci, veri):
    govde = istemci.get("/api/v1/bolumler").get_json()
    toplam = sum(b["student_count"] for b in govde["data"])
    assert toplam + govde["meta"]["unassigned_students"] == 2


# ---------- Sayfalama ----------

def test_sayfalama_ve_links(istemci, veri):
    govde = istemci.get("/api/v1/ogrenciler?page_size=1").get_json()
    assert len(govde["data"]) == 1
    assert govde["meta"]["total"] == 2
    assert govde["meta"]["total_pages"] == 2
    assert govde["links"]["next"] is not None
    assert govde["links"]["prev"] is None

    ikinci = istemci.get("/api/v1/ogrenciler?page=2&page_size=1").get_json()
    assert ikinci["links"]["next"] is None
    assert ikinci["links"]["prev"] is not None


# ---------- Filtreler ----------

@pytest.mark.parametrize("sorgu,bekle", [
    # "Guvenlik" degil "Guvenli": ogrencinin yetkinligi "Ag Guvenligi" ve
    # Turkce yumusama yuzunden (k -> g) alt dize eslesmez. Arama alt dize
    # temellidir, kok analizi yapmaz -- bilinen sinir.
    ("?skill=Guvenli", 1),
    ("?skill=python", 2),            # buyuk/kucuk harf duyarsiz
    ("?has_transcript=1", 1),
    ("?has_transcript=0", 1),
    ("?verified=1", 1),
    ("?min_completion=90", 1),       # dolu profil gecer
    ("?min_completion=1", 1),        # bos profil (0) dislanir
])
def test_filtreler(istemci, veri, sorgu, bekle):
    assert len(istemci.get("/api/v1/ogrenciler" + sorgu).get_json()["data"]) == bekle


def test_bolum_filtresi(istemci, veri, bolumler):
    govde = istemci.get(f"/api/v1/ogrenciler?department={bolumler[0]}").get_json()
    assert len(govde["data"]) == 1
    assert govde["data"][0]["department"] == bolumler[0]


# ---------- Hatalar ----------

@pytest.mark.parametrize("yol,kod,tur", [
    ("/api/v1/ogrenciler?page=0", 422, "invalid_parameter"),
    ("/api/v1/ogrenciler?page=abc", 422, "invalid_parameter"),
    ("/api/v1/ogrenciler?page_size=9999", 422, "invalid_parameter"),
    ("/api/v1/ogrenciler?min_completion=150", 422, "invalid_parameter"),
    ("/api/v1/ogrenciler/999999", 404, "not_found"),
    ("/api/v1/boyle-bir-sey-yok", 404, "not_found"),
])
def test_hatalar_json_donuyor(istemci, veri, yol, kod, tur):
    """API'de HTML hata sayfasi donseydi istemcinin ayristiricisi cokerdi."""
    cevap = istemci.get(yol)
    assert cevap.status_code == kod
    assert "application/json" in cevap.headers["Content-Type"]
    assert cevap.get_json()["error"]["type"] == tur


def test_yazma_metotlari_reddediliyor(istemci, veri):
    assert istemci.post("/api/v1/ozet").status_code == 405


# ---------- API anahtari ----------

@pytest.mark.parametrize("anahtar", [None, "yanlis-anahtar", "test-api-anahtar"])
def test_gecersiz_anahtar_401(istemci, veri, anahtar):
    basliklar = {"X-API-Key": anahtar} if anahtar else {}
    cevap = istemci.get("/api/v1/ozet/detay", headers=basliklar)
    assert cevap.status_code == 401
    assert cevap.get_json()["error"]["type"] == "unauthorized"


def test_dogru_anahtar_gecer(istemci, veri):
    cevap = istemci.get("/api/v1/ozet/detay", headers={"X-API-Key": API_ANAHTARI})
    assert cevap.status_code == 200
    govde = cevap.get_json()["data"]
    assert govde["approval_funnel"]["applied"] == 2
    assert govde["approval_funnel"]["approved"] == 1
    assert govde["messages"]["total"] == 1
    assert govde["messages"]["unread"] == 1
    assert len(govde["registrations_by_month"]) >= 1


# ---------- CSV ----------

CSV_UCLAR = [("/api/v1/ogrenciler", 13), ("/api/v1/bolumler", 6),
             ("/api/v1/yetkinlikler", 2)]


@pytest.mark.parametrize("yol,kolon", CSV_UCLAR)
def test_csv_basliklari(istemci, veri, yol, kolon):
    cevap = istemci.get(yol + "?format=csv")
    assert cevap.status_code == 200
    assert "text/csv" in cevap.headers["Content-Type"]
    assert "attachment" in cevap.headers["Content-Disposition"]
    ham = cevap.get_data()
    # BOM olmadan Excel dosyayi eski kod sayfasiyla acar, Turkce bozulur.
    assert ham[:3] == b"\xef\xbb\xbf"
    assert len(ham.decode("utf-8-sig").split("\r\n")[0].split(";")) == kolon


def test_csv_turkce_karakterleri_koruyor(istemci, veri):
    metin = istemci.get("/api/v1/ogrenciler?format=csv").get_data().decode("utf-8-sig")
    assert "Bilişim" in metin or "Teknolojisi" in metin
    assert "Ag Guvenligi" in metin


def test_csv_yetkinlik_hucresi_kolon_kaydirmiyor(istemci, veri):
    """Yetkinlikler tek hucrede birlesir; ayirici olarak ';' KULLANILMAMALI."""
    satirlar = istemci.get("/api/v1/ogrenciler?format=csv") \
                      .get_data().decode("utf-8-sig").split("\r\n")
    for satir in satirlar:
        if satir.strip():
            assert satir.count(";") == 12


def test_csv_virgul_secenegi(istemci, veri):
    baslik = istemci.get("/api/v1/ogrenciler?format=csv&delimiter=comma") \
                    .get_data().decode("utf-8-sig").split("\r\n")[0]
    assert baslik.count(",") == 12


def test_csv_filtreyle_birlesiyor(istemci, veri):
    def satir_sayisi(sorgu):
        metin = istemci.get(sorgu).get_data().decode("utf-8-sig")
        return len([s for s in metin.split("\r\n") if s.strip()])
    assert satir_sayisi("/api/v1/ogrenciler?min_completion=50&format=csv") \
         < satir_sayisi("/api/v1/ogrenciler?format=csv")


def test_csv_sayfalamayi_yoksayar(istemci, veri):
    """Excel'e aktaran veriyi butun ister, sayfa sayfa degil."""
    metin = istemci.get("/api/v1/ogrenciler?page_size=1&format=csv") \
                   .get_data().decode("utf-8-sig")
    assert len([s for s in metin.split("\r\n") if s.strip()]) == 3  # baslik + 2
