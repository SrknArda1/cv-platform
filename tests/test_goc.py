"""Goc (migration) zinciri: bos veritabanindan kurulum ve mevcut veritabani.

Komutlar alt surecte GERCEK "flask db ..." olarak calisir; app.py DATA_DIR'i
modul seviyesinde okudugu icin her test kendi gecici klasorunu ortam
degiskeniyle verir. Test surecinin kendi veritabanina dokunulmaz.
"""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
HEAD = "c4a1e07b92d5"


def _calistir(veri_klasoru, *argumanlar):
    """Alt surecte komut calistirir; Alembic logu stderr'e yazdigi icin
    iki cikti birlestirilir."""
    ortam = {**os.environ, "DATA_DIR": str(veri_klasoru), "FLASK_DEBUG": "1"}
    sonuc = subprocess.run(
        [sys.executable, *argumanlar], cwd=KOK, env=ortam,
        capture_output=True, text=True, encoding="utf-8",
    )
    cikti = sonuc.stdout + sonuc.stderr
    assert sonuc.returncode == 0, cikti
    return cikti


def _flask_db(veri_klasoru, *argumanlar):
    return _calistir(veri_klasoru, "-m", "flask", "--app", "app", "db", *argumanlar)


def _surum(veri_klasoru):
    with sqlite3.connect(veri_klasoru / "cv_platform.db") as c:
        return c.execute("select version_num from alembic_version").fetchone()[0]


def _isaret_ekle(veri_klasoru):
    with sqlite3.connect(veri_klasoru / "cv_platform.db") as c:
        c.execute("insert into user (email, password_hash, role, transcript_verified)"
                  " values ('isaret@test.local', 'x', 'student', 0)")


def _isaret_var_mi(veri_klasoru):
    with sqlite3.connect(veri_klasoru / "cv_platform.db") as c:
        return c.execute("select count(*) from user where email = 'isaret@test.local'"
                         ).fetchone()[0] == 1


def test_bos_veritabani_sifirdan_kurulur(tmp_path):
    """Yeni bir bilgisayarda ilk kurulum: zincir bastan sona calismali ve
    sonuc semasi modellerle birebir ayni olmali."""
    cikti = _flask_db(tmp_path, "upgrade")
    assert "-> 3fbf04b1f979" in cikti
    assert _surum(tmp_path) == HEAD

    # "db check" modellerle veritabani arasinda fark varsa hata koduyla doner.
    assert "No new upgrade operations detected" in _flask_db(tmp_path, "check")


def test_create_all_ile_kurulmus_veritabanina_dokunulmaz(tmp_path):
    """Canli veritabaninin durumu: create_all ile kurulmus ve head'e
    isaretlenmis. Baslangic gocu eklendikten sonra upgrade hicbir adim
    calistirmamali, veri yerinde kalmali."""
    _calistir(tmp_path, "-c", "from app import create_app; create_app()")
    _flask_db(tmp_path, "stamp", HEAD)
    _isaret_ekle(tmp_path)

    cikti = _flask_db(tmp_path, "upgrade")

    assert "Running upgrade" not in cikti
    assert _surum(tmp_path) == HEAD
    assert _isaret_var_mi(tmp_path)


def test_ara_surumdeki_veritabani_yalnizca_eksik_adimlari_calistirir(tmp_path):
    """Zincirin ortasindaki bir veritabani: yalnizca sonraki adimlar
    calismali, baslangic gocu tekrar calismamali."""
    _flask_db(tmp_path, "upgrade", "8fec39c31e99")
    _isaret_ekle(tmp_path)

    cikti = _flask_db(tmp_path, "upgrade")

    assert "8fec39c31e99 -> c4a1e07b92d5" in cikti
    assert "-> 3fbf04b1f979" not in cikti
    assert _isaret_var_mi(tmp_path)
