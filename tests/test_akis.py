"""Uctan uca is akisi: kurum basvurusu -> yonetici onayi -> aday havuzu ->
CV incelemesi -> mesaj -> ogrenci cevabi.

ERP'deki belge akisinin (siparis -> teslimat -> fatura -> tahsilat) bu
projedeki karsiligi: her adim bir oncekine BAGLI bir kayit uretir ve onceki
adim tamamlanmadan sonraki acilmaz. Adimlar gercek formlardan ve rotalardan
gecer; oturum kisayolu yalnizca yonetici icin kullanilir (yonetici hesabi
zaten web'den acilamiyor).
"""
from conftest import AD, EPOSTA, oturum_ac
from models import db, Message, User

KURUM_EPOSTA = "ik@yeni-kurum.test"
KURUM_SIFRE = "GucluSifre123"


def _kurum_giris(istemci):
    return istemci.post("/company/login",
                        data={"email": KURUM_EPOSTA, "password": KURUM_SIFRE})


def test_kurum_basvurusundan_ogrenci_cevabina_tam_akis(uygulama, veri):
    kurum = uygulama.test_client()

    # 1) Basvuru: kurum kendini kaydeder, hesap ONAYSIZ olusur
    yanit = kurum.post("/company/register", data={
        "email": KURUM_EPOSTA, "password": KURUM_SIFRE, "password2": KURUM_SIFRE,
        "company_name": "Yeni Kurum A.S.", "contact_person": "Insan Kaynaklari",
    })
    assert yanit.status_code == 302
    with uygulama.app_context():
        kayit = User.query.filter_by(email=KURUM_EPOSTA).one()
        kurum_id = kayit.id
        assert kayit.is_approved is False

    # 2) Onay olmadan sonraki adim kapali: giris reddedilir, havuz acilmaz
    yanit = _kurum_giris(kurum)
    assert yanit.headers["Location"].endswith("/company/login")
    assert kurum.get("/company/dashboard").status_code in (302, 403)

    # Ogrenci de onaysiz kuruma ilk mesaji baslatamaz
    ogrenci = uygulama.test_client()
    ogrenci.post("/student/login", data={"email": EPOSTA, "password": "sifre123"})
    assert ogrenci.get(f"/mesajlar/{kurum_id}").status_code == 403

    # 3) Onay: yonetici onaylar; kimin ve ne zaman onayladigi kaydedilir
    yonetici = oturum_ac(uygulama.test_client(), veri["yonetici"])
    assert yonetici.post(f"/admin/kurumlar/{kurum_id}/onayla").status_code == 302
    with uygulama.app_context():
        kayit = db.session.get(User, kurum_id)
        assert kayit.is_approved is True
        assert kayit.approved_at is not None
        assert kayit.approved_by.full_name == "Koordinator"   # denetim izi, iliski uzerinden

    # 4) Arama: onayli kurum giris yapar ve havuzda ogrenciyi bulur
    yanit = _kurum_giris(kurum)
    assert yanit.headers["Location"].endswith("/company/dashboard")
    havuz = kurum.get("/company/dashboard?q=Demirkan").get_data(as_text=True)
    assert AD in havuz

    # 5) Inceleme: CV ve PDF
    assert kurum.get(f"/company/student/{veri['dolu']}").status_code == 200
    assert kurum.get(f"/company/student/{veri['dolu']}/pdf").data[:4] == b"%PDF"

    # 6) Iletisim: kurum mesaj gonderir -> hareket kaydi olusur
    yanit = kurum.post(f"/mesajlar/{veri['dolu']}",
                       data={"body": "Staj programimiz icin gorusmek isteriz."})
    assert yanit.status_code == 302

    # 7) Ogrenci gelen kutusunda gorur ve artik cevap verebilir
    assert "Yeni Kurum A.S." in ogrenci.get("/mesajlar").get_data(as_text=True)
    konusma = ogrenci.get(f"/mesajlar/{kurum_id}")
    assert konusma.status_code == 200
    assert "Staj programimiz" in konusma.get_data(as_text=True)
    assert ogrenci.post(f"/mesajlar/{kurum_id}",
                        data={"body": "Tesekkurler, uygunum."}).status_code == 302

    # Zincirin tamami iliskilerle izlenebilir: mesaj -> kurum -> onaylayan
    with uygulama.app_context():
        mesajlar = (Message.query
                    .filter(db.or_(Message.sender_id == kurum_id,
                                   Message.recipient_id == kurum_id))
                    .order_by(Message.id).all())
        assert [m.sender.role for m in mesajlar] == ["company", "student"]
        assert mesajlar[0].recipient.full_name == AD
        assert mesajlar[0].sender.approved_by.role == "admin"
        assert mesajlar[1].read_at is None          # kurum henuz okumadi


def test_reddedilen_kurum_akisa_giremez(uygulama, veri):
    """Ret de bir akis sonucudur: gerekce kaydedilir, havuz kapali kalir."""
    kurum = uygulama.test_client()
    kurum.post("/company/register", data={
        "email": KURUM_EPOSTA, "password": KURUM_SIFRE, "password2": KURUM_SIFRE,
        "company_name": "Supheli Ltd.", "contact_person": "X",
    })
    with uygulama.app_context():
        kurum_id = User.query.filter_by(email=KURUM_EPOSTA).one().id

    yonetici = oturum_ac(uygulama.test_client(), veri["yonetici"])
    yonetici.post(f"/admin/kurumlar/{kurum_id}/reddet",
                  data={"reason": "Vergi kaydi dogrulanamadi"})

    with uygulama.app_context():
        kayit = db.session.get(User, kurum_id)
        assert kayit.basvuru_durumu == "reddedildi"
        assert kayit.rejected_by.full_name == "Koordinator"
        assert kayit.rejection_reason == "Vergi kaydi dogrulanamadi"
    assert _kurum_giris(kurum).headers["Location"].endswith("/company/login")
    assert kurum.get("/company/dashboard").status_code in (302, 403)
