"""REST API katmani -- /api/v1

Mevcut HTML sayfalarina hic dokunmadan, ayni veriyi program icin okunabilir
bicimde sunan IKINCI bir cikis. Ayri dosyada durmasinin sebebi app.py'nin
zaten 1500 satiri asmasi degil yalnizca; API kendi sozlesmesi olan ayri bir
katmandir: sayfalar insana, burasi makineye konusur.

TASARIM KARARLARI -- her biri savunulabilir olmali:

  * Surumleme ILK GUNDEN (/api/v1). Sonradan eklenemez: o noktada surumsuz
    calisan istemciler olur ve hepsi kirilir. /v2 acildiginda /v1 yasamaya
    devam eder.

  * Yalnizca GET. Dis sistemin veritabanimiza yazmasi gerekmiyor; salt-okunur
    bir API saldiri yuzeyini kucultur. POST/PUT/DELETE eslemesi bilinmiyor
    degil, GEREKMIYOR.

  * KISISEL VERI DONMEZ. Ad, e-posta, telefon ve transkript burada yoktur.
    Serilestirme katmani modeli degil, ACIKCA SECILEN alanlari doner -- modele
    yarin yeni bir kolon eklendiginde yanlislikla disari sizmasin diye.
    Veritabaninda gercek ogrencilerin verisi var; acik bir uc nokta sitenin
    tum giris korumasini baypas ederdi.

  * Ingilizce anahtar adlari. Turkce anahtarlar (bolum, dogrulandi) pandas ve
    Excel tarafinda kodlama sorunu cikarir; veriyi isleyen taraf icin pratik.

  * Her yanit ayni iskelette: data / meta / links. Hata da ayni bicimde doner,
    boylece istemci tek bir ayristirici yazar.
"""
import hmac
import os
from datetime import datetime
from functools import wraps

from flask import Blueprint, jsonify, request
from sqlalchemy.orm import selectinload

from models import db, User, Department, Certificate, Message

api = Blueprint("api", __name__, url_prefix="/api/v1")

SURUM = "1.0"
SAYFA_BOYUTU = 50
EN_BUYUK_SAYFA = 200

# Korumali uc nokta icin anahtar. Ortam degiskeninden okunur: kodda sabit
# anahtar tutmak, depoyu goren herkese anahtari vermek demektir.
# Tanimlanmamissa korumali uc nokta 503 doner -- sessizce acik kalmaz.
API_ANAHTARI = os.environ.get("API_ANAHTARI")


# ---------- Ortak yanit bicimi ----------

def _simdi():
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def yanit(data, meta=None, links=None):
    """Basarili yanit: data / meta / links."""
    govde = {
        "data": data,
        "meta": {"api_version": SURUM, "generated_at": _simdi(), **(meta or {})},
        "links": links or {},
    }
    return jsonify(govde), 200


def hata(kod, tur, mesaj):
    """Hata yaniti -- basariliyla AYNI iskelette.

    Istemci once durum kodunu okur; govdeyi ayristirmasi gerekirse yapisi
    degismedigi icin ayni kodla okuyabilir. HTML hata sayfasi donseydi
    ayristirici cokerdi.
    """
    govde = {
        "data": None,
        "error": {"status": kod, "type": tur, "message": mesaj},
        "meta": {"api_version": SURUM, "generated_at": _simdi()},
        "links": {},
    }
    return jsonify(govde), kod


def hata_yaniti(kod, baslik, aciklama):
    """app.py'deki GENEL hata isleyicilerinden cagrilir.

    Blueprint'in kendi errorhandler'lari yalnizca bu blueprint'in islevlerinde
    olusan hatalari yakalar. /api/v1/olmayan-adres gibi ESLESMEYEN bir yol
    uygulama seviyesinde 404 uretir ve oraya hic ugramaz -- o yuzden app.py
    tarafinda da bir kontrol gerekiyor.
    """
    turler = {
        400: "bad_request", 403: "forbidden", 404: "not_found",
        413: "payload_too_large", 429: "rate_limited", 500: "server_error",
    }
    return hata(kod, turler.get(kod, "error"), f"{baslik}. {aciklama}")


@api.after_request
def _api_basliklari(cevap):
    # CORS: tarayicidaki JavaScript'in baska bir alan adindan bu API'yi
    # okuyabilmesi icin gerekli. Sunucudan sunucuya cagrilarda (Python,
    # Postman, curl) devreye girmez -- same-origin policy tarayici kuralidir.
    # Veri anonim ve salt-okunur oldugu icin "*" guvenli.
    cevap.headers["Access-Control-Allow-Origin"] = "*"
    # Ayni sorgu arka arkaya gelirse istemci onbellekten okusun; sayimlar
    # saniyelik tazelik gerektirmiyor.
    cevap.headers["Cache-Control"] = "public, max-age=60"
    return cevap


# ---------- Kimlik dogrulama (middleware) ----------

def anahtar_gerekli(gorunum):
    """Korumali uc noktalar icin API anahtari denetimi.

    Dekorator, Flask'ta middleware'in karsiligidir: istek gorunum islevine
    ulasmadan once calisir ve zinciri kesebilir.
    """
    @wraps(gorunum)
    def sarmalanmis(*args, **kwargs):
        if not API_ANAHTARI:
            return hata(503, "not_configured",
                        "Bu uc nokta icin sunucuda API_ANAHTARI tanimlanmamis.")

        gelen = request.headers.get("X-API-Key", "")

        # hmac.compare_digest sabit surede karsilastirir. Siradan "==" ilk
        # farkli karakterde erken cikar; saldirgan yanit suresini olcerek
        # anahtari karakter karakter bulabilir (zamanlama saldirisi).
        if not hmac.compare_digest(gelen, API_ANAHTARI):
            return hata(401, "unauthorized",
                        "Gecersiz veya eksik API anahtari. X-API-Key basligi gonderin.")

        return gorunum(*args, **kwargs)
    return sarmalanmis


# ---------- Sorgu parametresi dogrulamasi ----------

def _tam_sayi(ad, varsayilan, en_az, en_cok):
    """Sorgu parametresini tam sayi olarak okur; sorun varsa mesaj doner."""
    ham = request.args.get(ad)
    if ham is None or ham == "":
        return varsayilan, None
    try:
        deger = int(ham)
    except ValueError:
        return None, f"'{ad}' tam sayi olmali, '{ham}' gonderildi."
    if deger < en_az or deger > en_cok:
        return None, f"'{ad}' {en_az} ile {en_cok} arasinda olmali, {deger} gonderildi."
    return deger, None


def _bayrak(ad):
    """?has_transcript=1 gibi ucuncu durumu olan bayrak: True / False / None."""
    ham = (request.args.get(ad) or "").strip().lower()
    if ham in ("1", "true", "evet"):
        return True
    if ham in ("0", "false", "hayir"):
        return False
    return None


# ---------- Serilestirme ----------
# Modeli dogrudan JSON'a cevirmiyoruz. Sebep: model yarin degisirse (yeni bir
# kolon eklenirse) o kolon kendiliginden disari sizardi. Burada her alan
# ACIKCA yaziliyor; yazilmayan hicbir sey disari cikmaz.

def _yetkinlikler(ham):
    if not ham:
        return []
    return [y.strip() for y in ham.split(",") if y.strip()]


def _tarih(deger):
    return deger.date().isoformat() if deger else None


def ogrenci_kaydi(ogrenci):
    """Tek ogrencinin ANONIM kaydi.

    Ad, e-posta, telefon ve transkript dosya adi BILEREK yoktur. Analiz icin
    kimlik gerekmiyor: bolum, ortalama ve yetkinlik dagilimi yeterli.
    """
    sertifikalar = ogrenci.certificates
    return {
        "id": ogrenci.id,
        "department": ogrenci.department or None,
        "gpa": ogrenci.gpa_value,
        "profile_completion": ogrenci.profile_completion(),
        "has_transcript": bool(ogrenci.transcript_filename),
        "transcript_verified": bool(ogrenci.transcript_verified),
        "education_count": len(ogrenci.educations),
        "experience_count": len(ogrenci.experiences),
        "certificate_count": len(sertifikalar),
        "verifiable_certificate_count": sum(1 for s in sertifikalar if s.dogrulanabilir),
        "project_count": len(ogrenci.projects),
        "skills": _yetkinlikler(ogrenci.skills),
        "registered_at": _tarih(ogrenci.created_at),
    }


def _ogrenci_sorgusu():
    """Ogrenci sorgusu + iliskilerin tek seferde yuklenmesi.

    selectinload olmasaydi her ogrenci icin ayri ayri egitim/deneyim/sertifika/
    proje sorgusu calisirdi (N+1 problemi): 50 ogrenciye 201 sorgu. Boyle 5
    sorgu yetiyor.
    """
    return User.query.filter_by(role="student").options(
        selectinload(User.educations),
        selectinload(User.experiences),
        selectinload(User.certificates),
        selectinload(User.projects),
    )


# ---------- Uc noktalar ----------

@api.route("/")
def kok():
    """API'nin kendini tanitmasi: hangi adresler var, ne doner."""
    return yanit({
        "name": "Kariyer Portali API",
        "version": SURUM,
        "description": "Ogrenci-kurum eslestirme platformunun anonim veri seti.",
        "privacy": "Kisisel veri (ad, e-posta, telefon, transkript) donmez.",
        "endpoints": [
            {"path": "/api/v1/ozet", "method": "GET", "returns": "Genel sayimlar"},
            {"path": "/api/v1/ogrenciler", "method": "GET", "returns": "Anonim ogrenci kayitlari (sayfalanmis)"},
            {"path": "/api/v1/ogrenciler/<id>", "method": "GET", "returns": "Tek ogrenci kaydi"},
            {"path": "/api/v1/bolumler", "method": "GET", "returns": "Bolum bazinda dagilim"},
            {"path": "/api/v1/yetkinlikler", "method": "GET", "returns": "Yetkinlik frekansi"},
            {"path": "/api/v1/ozet/detay", "method": "GET", "returns": "Ayrintili metrikler (X-API-Key gerekir)"},
        ],
        "filters": {
            "/api/v1/ogrenciler": [
                "page", "page_size", "department", "skill",
                "has_transcript", "verified", "min_completion",
            ]
        },
    })


@api.route("/ozet")
def ozet():
    """Tek bakista sayimlar -- analiz icin giris noktasi."""
    ogrenciler = _ogrenci_sorgusu().all()
    ortalamalar = [o.gpa_value for o in ogrenciler if o.gpa_value is not None]
    sertifika_sayisi = Certificate.query.count()
    dogrulanabilir = Certificate.query.filter(
        db.or_(Certificate.credential_url.isnot(None),
               Certificate.credential_id.isnot(None))
    ).count()

    return yanit({
        "students": {
            "total": len(ogrenciler),
            "with_transcript": sum(1 for o in ogrenciler if o.transcript_filename),
            "transcript_verified": sum(1 for o in ogrenciler if o.transcript_verified),
            "profile_complete": sum(1 for o in ogrenciler if o.profile_completion() >= 85),
            "average_gpa": round(sum(ortalamalar) / len(ortalamalar), 2) if ortalamalar else None,
        },
        "companies": {
            "total": User.query.filter_by(role="company").count(),
            "approved": User.query.filter_by(role="company", is_approved=True).count(),
            "pending": User.query.filter_by(role="company", is_approved=False).count(),
        },
        "certificates": {
            "total": sertifika_sayisi,
            "verifiable": dogrulanabilir,
            # Sertifikanin kaynagindan teyit edilebilirlik orani: dijital
            # dogrulama alanlarinin ne kadar benimsendigini gosterir.
            "verifiable_ratio": round(dogrulanabilir / sertifika_sayisi, 3) if sertifika_sayisi else None,
        },
        "departments": Department.query.count(),
    })


@api.route("/ogrenciler")
def ogrenciler():
    """Anonim ogrenci kayitlari -- sayfalanmis ve filtrelenebilir."""
    sayfa, mesaj = _tam_sayi("page", 1, 1, 10_000)
    if mesaj:
        return hata(422, "invalid_parameter", mesaj)
    boyut, mesaj = _tam_sayi("page_size", SAYFA_BOYUTU, 1, EN_BUYUK_SAYFA)
    if mesaj:
        return hata(422, "invalid_parameter", mesaj)
    en_az_doluluk, mesaj = _tam_sayi("min_completion", 0, 0, 100)
    if mesaj:
        return hata(422, "invalid_parameter", mesaj)

    sorgu = _ogrenci_sorgusu()
    bolum = (request.args.get("department") or "").strip()
    if bolum:
        sorgu = sorgu.filter(User.department == bolum)

    transkript = _bayrak("has_transcript")
    if transkript is True:
        sorgu = sorgu.filter(User.transcript_filename.isnot(None))
    elif transkript is False:
        sorgu = sorgu.filter(User.transcript_filename.is_(None))

    dogrulanmis = _bayrak("verified")
    if dogrulanmis is not None:
        sorgu = sorgu.filter(User.transcript_verified.is_(dogrulanmis))

    kayitlar = [ogrenci_kaydi(o) for o in sorgu.order_by(User.id).all()]

    # Yetkinlik ve doluluk filtreleri Python tarafinda: yetkinlikler virgulle
    # ayrilmis metin, doluluk ise iliskilerden HESAPLANAN bir deger -- ikisi de
    # SQL'de WHERE'e cevrilemiyor. Bu, veri modelinin bilinen zayif noktasi.
    yetkinlik = (request.args.get("skill") or "").strip().lower()
    if yetkinlik:
        kayitlar = [k for k in kayitlar
                    if any(yetkinlik in y.lower() for y in k["skills"])]
    if en_az_doluluk:
        kayitlar = [k for k in kayitlar if k["profile_completion"] >= en_az_doluluk]

    toplam = len(kayitlar)
    bas = (sayfa - 1) * boyut
    dilim = kayitlar[bas:bas + boyut]
    son_sayfa = max(1, -(-toplam // boyut))  # yukari yuvarlayan bolme

    def _adres(no):
        return f"/api/v1/ogrenciler?page={no}&page_size={boyut}"

    return yanit(dilim, meta={
        "total": toplam,
        "page": sayfa,
        "page_size": boyut,
        "total_pages": son_sayfa,
        "returned": len(dilim),
    }, links={
        "self": _adres(sayfa),
        "next": _adres(sayfa + 1) if sayfa < son_sayfa else None,
        "prev": _adres(sayfa - 1) if sayfa > 1 else None,
    })


@api.route("/ogrenciler/<int:ogrenci_id>")
def ogrenci(ogrenci_id):
    kayit = _ogrenci_sorgusu().filter(User.id == ogrenci_id).first()
    if kayit is None:
        return hata(404, "not_found", f"{ogrenci_id} numarali ogrenci bulunamadi.")
    return yanit(ogrenci_kaydi(kayit),
                 links={"self": f"/api/v1/ogrenciler/{ogrenci_id}"})


@api.route("/bolumler")
def bolumler():
    """Bolum bazinda dagilim -- ogrenci sayisi ve ortalama gostergeler."""
    ogrenciler_ = _ogrenci_sorgusu().all()
    sonuc = []
    for bolum in Department.query.order_by(Department.name).all():
        kume = [o for o in ogrenciler_ if o.department == bolum.name]
        ortalamalar = [o.gpa_value for o in kume if o.gpa_value is not None]
        sonuc.append({
            "id": bolum.id,
            "name": bolum.name,
            "student_count": len(kume),
            "with_transcript": sum(1 for o in kume if o.transcript_filename),
            "average_gpa": round(sum(ortalamalar) / len(ortalamalar), 2) if ortalamalar else None,
            "average_completion": round(sum(o.profile_completion() for o in kume) / len(kume), 1) if kume else None,
        })

    # Bolumu bos ya da artik var olmayan bir bolum olan ogrenciler: bolum
    # User tablosunda METIN tutuldugu icin bu kume olusabiliyor. Gizlemek
    # yerine raporluyoruz -- toplamlar tutsun.
    tanimli = {d.name for d in Department.query.all()}
    bosta = [o for o in ogrenciler_ if (o.department or "") not in tanimli]
    return yanit(sonuc, meta={"unassigned_students": len(bosta)})


@api.route("/yetkinlikler")
def yetkinlikler():
    """Yetkinlik frekansi -- analiz icin en verimli uc nokta."""
    sayim = {}
    for o in _ogrenci_sorgusu().all():
        for y in _yetkinlikler(o.skills):
            anahtar = y.lower()
            girdi = sayim.setdefault(anahtar, {"name": y, "student_count": 0})
            girdi["student_count"] += 1

    sirali = sorted(sayim.values(),
                    key=lambda g: (-g["student_count"], g["name"].lower()))
    return yanit(sirali, meta={"distinct_skills": len(sirali)})


@api.route("/ozet/detay")
@anahtar_gerekli
def ozet_detay():
    """Ayrintili metrikler -- API ANAHTARI gerektirir.

    Acik uc noktalardan farki, isletme tarafina ait sayimlar icermesi:
    kayit egrisi, onay hunisi, mesaj hacmi. Yine kisisel veri yok; buradaki
    koruma, verinin degeri kadar KIMLIK DOGRULAMA KATMANINI gostermek icin de
    var.
    """
    ogrenciler_ = _ogrenci_sorgusu().all()

    aylik = {}
    for o in User.query.all():
        if o.created_at:
            ay = o.created_at.strftime("%Y-%m")
            girdi = aylik.setdefault(ay, {"month": ay, "students": 0, "companies": 0})
            if o.role == "student":
                girdi["students"] += 1
            elif o.role == "company":
                girdi["companies"] += 1

    basamaklar = [0, 25, 50, 75, 85, 100]
    dagilim = []
    for i in range(len(basamaklar) - 1):
        alt, ust = basamaklar[i], basamaklar[i + 1]
        dagilim.append({
            "range": f"{alt}-{ust}",
            "student_count": sum(1 for o in ogrenciler_
                                 if alt <= o.profile_completion() < ust
                                 or (ust == 100 and o.profile_completion() == 100)),
        })

    return yanit({
        "registrations_by_month": sorted(aylik.values(), key=lambda g: g["month"]),
        "completion_distribution": dagilim,
        "approval_funnel": {
            "applied": User.query.filter_by(role="company").count(),
            "approved": User.query.filter_by(role="company", is_approved=True).count(),
            "rejected": User.query.filter(User.role == "company",
                                          User.rejected_at.isnot(None)).count(),
        },
        "messages": {
            "total": Message.query.count(),
            "unread": Message.query.filter(Message.read_at.is_(None)).count(),
        },
    })


# ---------- Blueprint'e ozel hatalar ----------
# /api/v1/ altinda olusan hatalar HTML sayfasi degil JSON donmeli; istemcinin
# ayristiricisi HTML gorurse coker.

@api.errorhandler(404)
def _api_404(e):
    return hata(404, "not_found", "Boyle bir uc nokta yok. /api/v1/ adresi listeler.")


@api.errorhandler(405)
def _api_405(e):
    return hata(405, "method_not_allowed",
                "Bu API salt-okunurdur, yalnizca GET kabul eder.")


@api.errorhandler(429)
def _api_429(e):
    return hata(429, "rate_limited",
                "Cok fazla istek gonderildi. Bir dakika bekleyip tekrar deneyin.")


@api.errorhandler(500)
def _api_500(e):
    return hata(500, "server_error", "Sunucuda beklenmedik bir hata olustu.")
