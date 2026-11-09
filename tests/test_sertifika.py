"""Sertifika dijital dogrulama alanlari ve adres sema denetimi."""
from io import BytesIO

import pytest

from conftest import oturum_ac
from app import guvenli_baglanti
from models import db, Certificate, Project


# ---------- guvenli_baglanti() ----------
# Jinja ozel karakterleri kacirir ama SEMAYI denetlemez: href="javascript:..."
# yazan bir ogrencinin baglantisina tiklayan kurum o kodu kendi oturumunda
# calistirirdi (depolanmis XSS).

@pytest.mark.parametrize("giris,bekle", [
    ("https://credly.com/badges/x", "https://credly.com/badges/x"),
    ("http://ornek.com/a", "http://ornek.com/a"),
    # Semasiz yazilan adres reddedilmez, https eklenir -- insanlar adresi
    # cogu zaman boyle kopyaliyor.
    ("credly.com/badges/x", "https://credly.com/badges/x"),
    ("www.coursera.org/verify/AB", "https://www.coursera.org/verify/AB"),
    ("  credly.com/x  ", "https://credly.com/x"),
])
def test_gecerli_adresler_gecer(giris, bekle):
    assert guvenli_baglanti(giris) == bekle


@pytest.mark.parametrize("zararli", [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "data:text/html,<script>",
    "vbscript:msgbox",
    "file:///C:/Windows",
])
def test_zararli_semalar_temizlenir(zararli):
    assert guvenli_baglanti(zararli) == ""


@pytest.mark.parametrize("bos", ["", None, "   "])
def test_bos_deger(bos):
    assert guvenli_baglanti(bos) == ""


# ---------- Form kaydi ----------

def _cv_gonder(istemci, **fazla):
    alanlar = {
        "full_name": "Test Ogrenci", "department": "", "phone": "",
        "summary": "", "skills": "Python",
    }
    alanlar.update(fazla)
    return istemci.post("/student/cv", data=alanlar, follow_redirects=True)


def test_dogrulama_alanlari_kaydediliyor(istemci, veri, uygulama):
    oturum_ac(istemci, veri["bos"])
    cevap = _cv_gonder(
        istemci,
        **{"cert_name[]": ["AWS Cloud Practitioner"],
           "cert_institution[]": ["Amazon"],
           "cert_date[]": ["2024"],
           "cert_credential_id[]": ["AWS-PSA-12345"],
           "cert_credential_url[]": ["credly.com/badges/abc"]})
    assert cevap.status_code == 200

    with uygulama.app_context():
        kayit = Certificate.query.filter_by(student_id=veri["bos"]).one()
        assert kayit.credential_id == "AWS-PSA-12345"
        # Semasiz girildi, sunucu https ekledi
        assert kayit.credential_url == "https://credly.com/badges/abc"
        assert kayit.dogrulanabilir is True


def test_zararli_adres_kaydedilmez(istemci, veri, uygulama):
    oturum_ac(istemci, veri["bos"])
    _cv_gonder(istemci,
               **{"cert_name[]": ["Kotu Adres"],
                  "cert_institution[]": ["X"],
                  "cert_date[]": [""],
                  "cert_credential_id[]": [""],
                  "cert_credential_url[]": ["javascript:alert(document.cookie)"]})
    with uygulama.app_context():
        kayit = Certificate.query.filter_by(student_id=veri["bos"]).one()
        assert kayit.credential_url == ""
        assert bool(kayit.dogrulanabilir) is False


def test_yalnizca_belge_no_da_dogrulanabilir_sayilir(istemci, veri, uygulama):
    oturum_ac(istemci, veri["bos"])
    _cv_gonder(istemci,
               **{"cert_name[]": ["Sadece No"], "cert_institution[]": [""],
                  "cert_date[]": [""], "cert_credential_id[]": ["ABC123"],
                  "cert_credential_url[]": [""]})
    with uygulama.app_context():
        assert Certificate.query.filter_by(student_id=veri["bos"]).one().dogrulanabilir


def test_proje_baglantisi_da_denetleniyor(istemci, veri, uygulama):
    """Ayni acik projelerde de vardi; tek yardimci iki yeri birden kapatiyor."""
    oturum_ac(istemci, veri["bos"])
    _cv_gonder(istemci,
               **{"proj_title[]": ["Kotu Proje"], "proj_description[]": [""],
                  "proj_tech_stack[]": [""],
                  "proj_link[]": ["javascript:alert(1)"]})
    with uygulama.app_context():
        assert Project.query.filter_by(student_id=veri["bos"]).one().link == ""


# ---------- Form yeniden aciliyor ----------

def test_form_kayitli_degerleri_gosteriyor(istemci, veri):
    oturum_ac(istemci, veri["dolu"])
    sayfa = istemci.get("/student/cv").get_data(as_text=True)
    assert 'name="cert_credential_id[]"' in sayfa
    assert 'name="cert_credential_url[]"' in sayfa
    assert 'value="AWS-PSA-12345"' in sayfa


def test_bos_satir_sablonunda_undefined_yok(istemci, veri):
    """namespace() yeni alanlari tanimlamazsa '+ Sertifika ekle' bozulur."""
    oturum_ac(istemci, veri["dolu"])
    sayfa = istemci.get("/student/cv").get_data(as_text=True)
    sablon = sayfa.split('id="cert-row-template"')[1].split("</template>")[0]
    assert "Undefined" not in sablon
    assert "None" not in sablon


# ---------- CV sayfasi ----------

def test_cv_sayfasinda_dogrulama_gorunuyor(istemci, veri):
    oturum_ac(istemci, veri["dolu"])
    sayfa = istemci.get("/student/preview").get_data(as_text=True)
    assert "Belge no AWS-PSA-12345" in sayfa
    assert 'href="https://www.credly.com/badges/abc"' in sayfa


def test_cv_sayfasinda_javascript_semasi_yok(istemci, veri):
    oturum_ac(istemci, veri["dolu"])
    assert "javascript:" not in istemci.get("/student/preview") \
                                       .get_data(as_text=True).lower()


def test_adressiz_sertifikada_baglanti_basilmaz(istemci, veri):
    """Iki sertifika var, yalnizca birinin adresi -- tek baglanti cikmali."""
    oturum_ac(istemci, veri["dolu"])
    sayfa = istemci.get("/student/preview").get_data(as_text=True)
    assert sayfa.count('class="entry-link"') == 1


# ---------- PDF ----------

def test_pdf_uretiliyor_ve_alanlari_tasiyor(istemci, veri):
    oturum_ac(istemci, veri["dolu"])
    cevap = istemci.get("/student/cv-pdf")
    assert cevap.status_code == 200
    ham = cevap.get_data()
    assert ham[:4] == b"%PDF"

    pypdf = pytest.importorskip("pypdf")
    sayfa = pypdf.PdfReader(BytesIO(ham)).pages[0]
    metin = sayfa.extract_text() or ""
    duz = "".join(metin.split())
    assert "AWS-PSA-12345" in duz
    # Fontlar pdfmetrics ile kaydedilmezse Turkce harfler kare kutu olur.
    assert "\u25a0" not in metin


def test_pdf_uzun_adresi_kesmeden_yaziyor(istemci, veri, uygulama):
    uzun = "https://www.credly.com/badges/1a2b3c4d-5e6f-7890-abcd-ef1234567890/public_url"
    with uygulama.app_context():
        kayit = (Certificate.query.filter_by(student_id=veri["dolu"])
                 .order_by(Certificate.id).first())
        kayit.credential_url = uzun
        db.session.commit()

    oturum_ac(istemci, veri["dolu"])
    ham = istemci.get("/student/cv-pdf").get_data()
    pypdf = pytest.importorskip("pypdf")
    metin = pypdf.PdfReader(BytesIO(ham)).pages[0].extract_text() or ""
    assert "public_url" in "".join(metin.split())


@pytest.mark.parametrize("template_id", range(1, 7))
def test_cv_sablonlari_pdf_olarak_indiriliyor(istemci, veri, template_id):
    oturum_ac(istemci, veri["dolu"])

    cevap = istemci.get(f"/download_template/{template_id}")

    assert cevap.status_code == 200
    assert cevap.data.startswith(b"%PDF")
    assert cevap.mimetype == "application/pdf"
    assert "attachment;" in cevap.headers["Content-Disposition"]
    assert "Ayse_Yilmaz_Demirkan_cv.pdf" in cevap.headers["Content-Disposition"]


@pytest.mark.parametrize("template_id", [0, 7])
def test_gecersiz_cv_sablon_idsi_bulunamadi_doner(istemci, veri, template_id):
    oturum_ac(istemci, veri["dolu"])

    assert istemci.get(f"/download_template/{template_id}").status_code == 404
