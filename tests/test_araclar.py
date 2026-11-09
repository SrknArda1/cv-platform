"""Ana veri gocu (bolum-ice-aktar), yedekleme (yedekle), pandas raporu ve
sayfalardaki JavaScript baglantilari."""
import io
import os
import shutil
import sqlite3
import sys

import pytest

import app as uygulama_modulu
from conftest import KOK, oturum_ac
from models import db, Department

sys.path.insert(0, str(KOK / "araclar"))


def _bolumler(uygulama):
    with uygulama.app_context():
        return sorted(d.name for d in Department.query.all())


def _aktar(uygulama, tmp_path, icerik, *secenekler):
    dosya = tmp_path / "bolumler.csv"
    dosya.write_text(icerik, encoding="utf-8")
    return uygulama.test_cli_runner().invoke(
        args=["bolum-ice-aktar", str(dosya), *secenekler])


# ---------- bolum-ice-aktar ----------

def test_ice_aktarma_mukerrer_ve_bos_satirlari_atlar(uygulama, tmp_path):
    # Kayitlilar: "Fiber Teknolojisi", "Kurumsal Bilişim" (seed_departments)
    sonuc = _aktar(uygulama, tmp_path,
                   "name\n"
                   "Yazılım Mühendisliği\n"
                   "KURUMSAL BİLİŞİM\n"          # kayitli, buyuk harf + Turkce İ
                   "  fiber   teknolojisi \n"    # kayitli, bosluk farki
                   "   \n"                       # yalnizca bosluk; tam bos satiri csv zaten atlar
                   "yazılım  mühendisliği\n"     # dosya icinde tekrar
                   "Endüstri Mühendisliği\n")

    assert sonuc.exit_code == 0, sonuc.output
    assert "Eklenecek          : 2" in sonuc.output
    assert "Zaten kayitli      : 2" in sonuc.output
    assert "Dosyada tekrar     : 1" in sonuc.output
    assert "Bos satir          : 1" in sonuc.output
    assert _bolumler(uygulama) == ["Endüstri Mühendisliği", "Fiber Teknolojisi",
                                   "Kurumsal Bilişim", "Yazılım Mühendisliği"]


def test_ice_aktarma_iki_kez_calisinca_ikinci_sefer_eklemez(uygulama, tmp_path):
    icerik = "name\nYazılım Mühendisliği\n"
    _aktar(uygulama, tmp_path, icerik)

    sonuc = _aktar(uygulama, tmp_path, icerik)

    assert "Eklenecek          : 0" in sonuc.output
    assert len(_bolumler(uygulama)) == 3


def test_kuru_calistirma_hicbir_sey_yazmaz(uygulama, tmp_path):
    sonuc = _aktar(uygulama, tmp_path, "name\nYazılım Mühendisliği\n", "--kuru")

    assert sonuc.exit_code == 0
    assert "hicbir sey yazilmadi" in sonuc.output
    assert len(_bolumler(uygulama)) == 2


def test_noktali_virgullu_excel_dosyasi_ve_bolum_kolonu(uygulama, tmp_path):
    sonuc = _aktar(uygulama, tmp_path,
                   "﻿kod;bolum\n1;Makine Mühendisliği\n2;Elektrik Mühendisliği\n")

    assert sonuc.exit_code == 0, sonuc.output
    assert "Makine Mühendisliği" in _bolumler(uygulama)


def test_kolon_yoksa_hata_verir_ve_yazmaz(uygulama, tmp_path):
    sonuc = _aktar(uygulama, tmp_path, "ad;soyad\nAli;Veli\n")

    assert sonuc.exit_code != 0
    assert "kolonu bulunamadi" in sonuc.output
    assert len(_bolumler(uygulama)) == 2


def test_uzun_ad_tum_aktarimi_durdurur(uygulama, tmp_path):
    sonuc = _aktar(uygulama, tmp_path, "name\nKisa Bolum\n" + "x" * 121 + "\n")

    assert sonuc.exit_code != 0
    assert len(_bolumler(uygulama)) == 2


# ---------- yedekle ----------

@pytest.fixture
def yedek_klasoru():
    klasor = os.path.join(uygulama_modulu.DATA_DIR, "yedekler")
    shutil.rmtree(klasor, ignore_errors=True)
    yield klasor
    shutil.rmtree(klasor, ignore_errors=True)


def test_yedek_tutarli_ve_veriyi_icerir(uygulama, yedek_klasoru):
    sonuc = uygulama.test_cli_runner().invoke(args=["yedekle"])

    assert sonuc.exit_code == 0, sonuc.output
    assert "butunluk: ok" in sonuc.output
    (dosya,) = os.listdir(yedek_klasoru)
    # "with sqlite3.connect()" baglantiyi KAPATMAZ; Windows'ta dosya kilitli kalir
    c = sqlite3.connect(os.path.join(yedek_klasoru, dosya))
    try:
        adlar = {r[0] for r in c.execute("select name from departments")}
    finally:
        c.close()
    assert adlar == {"Fiber Teknolojisi", "Kurumsal Bilişim"}


def test_yedek_yalnizca_en_yeni_n_tanesini_tutar(uygulama, yedek_klasoru):
    os.makedirs(yedek_klasoru)
    for gun in range(1, 6):  # 5 eski yedek
        open(os.path.join(yedek_klasoru, f"cv_platform-2020010{gun}-000000.db"), "w").close()
    yabanci = os.path.join(yedek_klasoru, "elle-alinan.db")
    open(yabanci, "w").close()

    sonuc = uygulama.test_cli_runner().invoke(args=["yedekle", "--sakla", "3"])

    assert sonuc.exit_code == 0, sonuc.output
    kalan = sorted(f for f in os.listdir(yedek_klasoru) if f.startswith("cv_platform-"))
    assert len(kalan) == 3
    assert "cv_platform-20200105-000000.db" in kalan   # en yeni eskiler kalir
    assert "cv_platform-20200101-000000.db" not in kalan
    assert os.path.exists(yabanci)                     # adlandirmaya uymayana dokunulmaz


# ---------- pandas raporu ----------

pd = pytest.importorskip("pandas")
import yetkinlik_raporu as rapor  # noqa: E402

API_CSV = (
    "﻿id;department;gpa;profile_completion;has_transcript;skills\r\n"
    "1;Fiber;3,40;100;evet;Python | SQL | Git\r\n"
    "2;Fiber;2.60;40;hayir;python | SQL\r\n"
    "3;Kurumsal;;70;evet;Python | Excel\r\n"
    "4;;3,00;20;hayir;\r\n"
)


def _ogrenciler():
    return rapor.veriyi_oku(io.StringIO(API_CSV))


def test_abc_analizi_siniflari_ve_kumulatif_pay():
    abc = rapor.abc_analizi(_ogrenciler()).set_index("yetkinlik")

    # Python 3 ogrencide (python/Python ayni sayilir), toplam 7 bahsedilme
    assert abc.loc["Python", "ogrenci_sayisi"] == 3
    assert abc["ogrenci_sayisi"].sum() == 7
    assert abc["kumulatif_yuzde"].iloc[-1] == 100.0
    # Python %0'dan, SQL %42,9'dan baslar -> A; Excel %71,4 -> A; Git %85,7 -> B
    assert abc["sinif"].to_dict() == {"Python": "A", "SQL": "A", "Excel": "A", "Git": "B"}


def test_bolum_ozeti_virgullu_notu_ve_bolumsuzu_isler():
    ozet = rapor.bolum_ozeti(_ogrenciler()).set_index("department")

    assert ozet.loc["Fiber", "ogrenci"] == 2
    assert ozet.loc["Fiber", "ortalama_not"] == 3.0          # (3,40 + 2,60) / 2
    assert ozet.loc["Fiber", "transkript_orani"] == 50.0
    assert ozet.loc["(bolumsuz)", "ogrenci"] == 1


def test_kayit_tahmini_mape_ve_bias():
    """Elle dogrulanabilir ornek: Oca 2, Sub 1, Mar 3, Nis 0 (bos ay), May 1.

    Nisan tahmini (2+1+3)/3 = 2, gercek 0 -> hata +2, MAPE'ye katilmaz (0'a bolunemez).
    Mayis tahmini (1+3+0)/3 = 1,33, gercek 1 -> hata +0,33, yuzde hata %33,3.
    """
    kayitlar = pd.DataFrame({"registered_at": [
        "2026-01-05", "2026-01-20", "2026-02-03",
        "2026-03-10", "2026-03-11", "2026-03-12", "2026-05-01"]})

    tablo, ozet = rapor.kayit_tahmini(kayitlar)

    assert tablo["gercek"].tolist() == [2, 1, 3, 0, 1]         # bos ay 0 olarak eklendi
    assert tablo["tahmin"].isna().tolist() == [True, True, True, False, False]
    assert ozet["degerlendirilen_ay"] == 2
    assert ozet["mape"] == 33.3                               # yuvarlanmamis tahminden
    assert ozet["bias"] == 1.17                               # (2 + 0,33) / 2: fazla tahmin
    assert ozet["sonraki_ay"] == "2026-06"
    assert ozet["sonraki_ay_tahmini"] == 1.3                  # (3 + 0 + 1) / 3


def test_kayit_tahmini_tarih_yoksa_bos_doner():
    tablo, ozet = rapor.kayit_tahmini(pd.DataFrame({"registered_at": [None, ""]}))

    assert tablo.empty and ozet == {}


def test_rapor_api_csvsini_okuyup_dosya_yazar(istemci, veri, tmp_path):
    """Uctan uca: gercek API ciktisi -> pandas -> CSV dosyalari."""
    csv_dosyasi = tmp_path / "ogrenciler.csv"
    csv_dosyasi.write_bytes(istemci.get("/api/v1/ogrenciler?format=csv").data)

    assert rapor.main(["--kaynak", str(csv_dosyasi), "--cikti", str(tmp_path)]) == 0

    abc = pd.read_csv(tmp_path / "yetkinlik_abc.csv", sep=";", encoding="utf-8-sig")
    assert abc.iloc[0]["yetkinlik"] == "Python"    # iki ogrencide de var
    assert (tmp_path / "bolum_ozeti.csv").exists()
    assert (tmp_path / "kayit_tahmini.csv").exists()


# ---------- sayfalardaki JavaScript baglantilari ----------

def test_genel_bakis_grafigi_api_adresini_ve_kutuphaneyi_yukler(istemci, veri):
    oturum_ac(istemci, veri["yonetici"])

    html = istemci.get("/admin").get_data(as_text=True)

    assert 'data-kaynak="/api/v1/yetkinlikler"' in html
    assert "vendor/chart.umd.min.js" in html
    assert "admin_charts.js" in html
    # Grafigin fetch ile cektigi uc nokta girissiz ve anahtarsiz JSON donmeli
    yanit = istemci.get("/api/v1/yetkinlikler")
    assert yanit.status_code == 200 and yanit.is_json


def test_statik_js_dosyalari_sunulur(istemci):
    for yol in ("/static/admin_charts.js", "/static/vendor/chart.umd.min.js",
                "/static/main.js"):
        assert istemci.get(yol).status_code == 200, yol


def test_cv_formu_canli_doluluk_gostergesi_tasir(istemci, veri):
    oturum_ac(istemci, veri["dolu"])

    html = istemci.get("/student/cv").get_data(as_text=True)

    assert "data-live-completion" in html
    assert 'data-has-transcript="1"' in html
    assert "%100" in html          # sunucunun hesapladigi ilk deger
    # Istemci tarafi boyut denetimi sunucudaki 10 MB sinirla ayni olmali
    assert html.count('data-max-mb="10"') == 2
    assert uygulama_modulu.app.config["MAX_CONTENT_LENGTH"] == 10 * 1024 * 1024


def test_ogrenci_listesi_anlik_arama_kutusu_tasir(istemci, veri):
    oturum_ac(istemci, veri["yonetici"])

    html = istemci.get("/admin/ogrenciler").get_data(as_text=True)

    assert 'data-live-search="ogrenci-tablosu"' in html
    assert 'id="ogrenci-tablosu"' in html
    assert "data-live-count" in html
