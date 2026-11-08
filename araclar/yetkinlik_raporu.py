"""Yetkinlik ve bolum raporu: API'den CSV cekip pandas ile analiz eder.

Kariyer merkezi icin uc soru cevaplar:
  1. Ogrencilerde hangi yetkinlikler yogun? -> ABC (Pareto) analizi
  2. Bolumler profil kalitesi bakimindan nasil? -> bolum ozeti
  3. Gelecek ay kac yeni kayit beklenir? -> talep tahmini, MAPE ve bias
     (koordinatorun transkript dogrulama is yukunu planlamak icin)

Veri kaynagi platformun kendi REST API'si (anonim, kisisel veri yok).
Bu, ders kitabindaki "API ile entegrasyon" ilkesinin ornegi: rapor araci
veritabanina dogrudan baglanmaz, yalnizca yayinlanan arayuzu kullanir.

Kullanim:
    python araclar/yetkinlik_raporu.py                         # yerel sunucu
    python araclar/yetkinlik_raporu.py --kaynak https://.../api/v1/ogrenciler?format=csv
    python araclar/yetkinlik_raporu.py --kaynak indirilen.csv  # dosyadan

Cikti: ekrana tablo, rapor/ klasorune uc CSV (Excel'de acilir).
pandas yalnizca gelistirme bagimliligidir (requirements-dev.txt); sunucuya
kurulmaz.
"""
import argparse
from pathlib import Path

import click
import pandas as pd

VARSAYILAN_KAYNAK = "http://127.0.0.1:5000/api/v1/ogrenciler?format=csv"
ABC_SINIRLARI = (80, 95)  # kumulatif pay: %80'e kadar A, %95'e kadar B
TAHMIN_PENCERESI = 3       # hareketli ortalama: son 3 ayin ortalamasi


def veriyi_oku(kaynak):
    """API CSV'si ';' ayiricili ve BOM'ludur (Excel icin); pandas ikisini de
    okur. Yetkinlikler tek hucrede ' | ' ile birlestirilmistir."""
    return pd.read_csv(kaynak, sep=";", encoding="utf-8-sig")


def abc_analizi(ogrenciler):
    """Her yetkinligin kac ogrencide gectigini sayar ve ABC sinifi verir.

    Sinif, yetkinlik eklenmeden ONCEKI kumulatif paya gore verilir: en sik
    yetkinlik tek basina %80'i assa bile A olur.
    """
    yetkinlikler = (
        ogrenciler["skills"].dropna().astype(str)
        .str.split(r"\s*\|\s*").explode().str.strip()
    )
    yetkinlikler = yetkinlikler[yetkinlikler != ""]
    # Ayni yetkinligin farkli yazimlari (python / Python) tek kalem sayilir
    anahtar = yetkinlikler.str.casefold()
    gorunen_ad = yetkinlikler.groupby(anahtar).agg(lambda s: s.mode().iloc[0])

    tablo = (anahtar.value_counts().rename("ogrenci_sayisi").to_frame()
             .rename_axis("anahtar").reset_index())
    tablo["yetkinlik"] = tablo["anahtar"].map(gorunen_ad)
    tablo = tablo.sort_values(["ogrenci_sayisi", "yetkinlik"],
                              ascending=[False, True], ignore_index=True)

    toplam = tablo["ogrenci_sayisi"].sum()
    tablo["pay_yuzde"] = (tablo["ogrenci_sayisi"] / toplam * 100).round(1)
    kumulatif = tablo["ogrenci_sayisi"].cumsum() / toplam * 100
    onceki = kumulatif - tablo["ogrenci_sayisi"] / toplam * 100
    tablo["kumulatif_yuzde"] = kumulatif.round(1)
    a_siniri, b_siniri = ABC_SINIRLARI
    tablo["sinif"] = onceki.map(
        lambda pay: "A" if pay < a_siniri else "B" if pay < b_siniri else "C")
    return tablo[["yetkinlik", "ogrenci_sayisi", "pay_yuzde",
                  "kumulatif_yuzde", "sinif"]]


def bolum_ozeti(ogrenciler):
    """Bolum bazinda ogrenci sayisi, ortalama not, doluluk ve transkript orani."""
    df = ogrenciler.copy()
    df["department"] = df["department"].fillna("(bolumsuz)")
    # Not ondalik virgulle de girilmis olabilir ("3,10"); sayiya cevrilemeyen bos kalir
    df["gpa"] = pd.to_numeric(df["gpa"].astype(str).str.replace(",", "."), errors="coerce")
    df["transkript"] = df["has_transcript"].eq("evet")

    ozet = df.groupby("department").agg(
        ogrenci=("id", "count"),
        ortalama_not=("gpa", "mean"),
        ortalama_doluluk=("profile_completion", "mean"),
        transkript_orani=("transkript", "mean"),
    )
    ozet["ortalama_not"] = ozet["ortalama_not"].round(2)
    ozet["ortalama_doluluk"] = ozet["ortalama_doluluk"].round(1)
    ozet["transkript_orani"] = (ozet["transkript_orani"] * 100).round(1)
    return ozet.sort_values("ogrenci", ascending=False).reset_index()


def kayit_tahmini(ogrenciler, pencere=TAHMIN_PENCERESI):
    """Aylik yeni ogrenci kaydi icin hareketli ortalama tahmini ve dogrulugu.

    Talep = ay icinde kaydolan ogrenci sayisi. Her ayin tahmini, ONCEKI
    `pencere` ayin ortalamasidir (o ayin kendi verisi kullanilmaz). Gecmis
    aylarda tahmin ile gercek karsilastirilir:

      MAPE = ortalama(|gercek - tahmin| / gercek) x 100   (yuzde hata)
      Bias = ortalama(tahmin - gercek)                    (+ fazla, - eksik tahmin)

    Gercegi 0 olan aylar MAPE'ye katilmaz (sifira bolunemez), bias'a katilir.
    Donus: (aylik tablo, ozet sozlugu).
    """
    tarih = pd.to_datetime(ogrenciler["registered_at"], errors="coerce").dropna()
    if tarih.empty:
        return pd.DataFrame(), {}
    sayim = tarih.dt.to_period("M").value_counts().sort_index()
    # Hic kayit olmayan aylar da seride 0 olarak yer almali
    tum_aylar = pd.period_range(sayim.index.min(), sayim.index.max(), freq="M")
    gercek = sayim.reindex(tum_aylar, fill_value=0)

    # Hesap yuvarlanmamis degerlerle yapilir; yalnizca tablo gosterimi yuvarlanir
    tahmin = gercek.rolling(pencere).mean().shift(1)
    hata = tahmin - gercek
    yuzde_hata = hata.abs() / gercek.where(gercek > 0) * 100

    tablo = pd.DataFrame({
        "ay": gercek.index.astype(str), "gercek": gercek.values,
        "tahmin": tahmin.round(1).values, "hata": hata.round(1).values,
        "mutlak_yuzde_hata": yuzde_hata.round(1).values,
    })

    degerlendirilen = tahmin.notna()
    mape = yuzde_hata[degerlendirilen].mean()
    bias = hata[degerlendirilen].mean()
    ozet = {
        "yontem": f"{pencere} aylik hareketli ortalama",
        "degerlendirilen_ay": int(degerlendirilen.sum()),
        "mape": None if pd.isna(mape) else round(float(mape), 1),
        "bias": None if pd.isna(bias) else round(float(bias), 2),
        "sonraki_ay": (gercek.index.max() + 1).strftime("%Y-%m"),
        "sonraki_ay_tahmini": round(float(gercek.tail(pencere).mean()), 1)
        if len(gercek) >= pencere else None,
    }
    return tablo, ozet


def main(argv=None):
    ayrac = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayrac.add_argument("--kaynak", default=VARSAYILAN_KAYNAK,
                       help="API CSV adresi veya yerel CSV dosyasi")
    ayrac.add_argument("--cikti", default="rapor", help="CSV'lerin yazilacagi klasor")
    secenek = ayrac.parse_args(argv)

    ogrenciler = veriyi_oku(secenek.kaynak)
    if ogrenciler.empty:
        click.echo("Kaynakta ogrenci kaydi yok.")
        return 1

    abc = abc_analizi(ogrenciler)
    bolumler = bolum_ozeti(ogrenciler)
    tahmin, tahmin_ozeti = kayit_tahmini(ogrenciler)

    cikti = Path(secenek.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    # utf-8-sig + ';' : Turkce Excel'de dogrudan acilsin
    abc.to_csv(cikti / "yetkinlik_abc.csv", sep=";", index=False, encoding="utf-8-sig")
    bolumler.to_csv(cikti / "bolum_ozeti.csv", sep=";", index=False, encoding="utf-8-sig")
    tahmin.to_csv(cikti / "kayit_tahmini.csv", sep=";", index=False, encoding="utf-8-sig")

    with pd.option_context("display.width", 120, "display.max_rows", 40):
        click.echo(f"\n{len(ogrenciler)} ogrenci, {len(abc)} farkli yetkinlik\n")
        click.echo(f"ABC sinif dagilimi: {abc['sinif'].value_counts().sort_index().to_dict()}")
        click.echo("\nYetkinlik ABC analizi (ilk 15):")
        click.echo(abc.head(15).to_string(index=False))
        click.echo("\nBolum ozeti:")
        click.echo(bolumler.to_string(index=False))
        if tahmin_ozeti:
            click.echo(f"\nAylik kayit talebi tahmini ({tahmin_ozeti['yontem']}):")
            click.echo(tahmin.to_string(index=False))
            click.echo(f"MAPE: %{tahmin_ozeti['mape']}  |  Bias: {tahmin_ozeti['bias']} kayit/ay "
                       f"({tahmin_ozeti['degerlendirilen_ay']} ay uzerinden)")
            click.echo(f"{tahmin_ozeti['sonraki_ay']} tahmini: {tahmin_ozeti['sonraki_ay_tahmini']} yeni kayit")
    click.echo(f"\nCSV'ler yazildi: {cikti.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
