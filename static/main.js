document.addEventListener("DOMContentLoaded", () => {
  initMobileMenu();
  initTabs();
  initDynamicRows();
  initUnsavedGuard();
  initConfirmForms();
  initLiveCompletion();
  initLiveSearch();
  initFileSizeGuard();
  initPasswordMatch();
  initCvRowWarnings();
});

/* --------------------------------------------------------------------------
   İstemci tarafı doğrulama ve anlık uyarılar

   Sunucu doğrulaması (app.py) asıl korumadır; buradakiler kullanıcıyı
   formu göndermeden ÖNCE uyarır. İki tür var:
     - Engelleyen (setCustomValidity): sunucunun da reddedeceği durumlar
       (10 MB'ı aşan dosya, eşleşmeyen şifre). Form gönderilmez.
     - Yalnızca uyaran: sunucunun kabul ettiği ama büyük olasılıkla yanlış
       girilmiş değerler (not aralığı, bitiş yılı < başlangıç yılı).
   -------------------------------------------------------------------------- */

function uyariGoster(alan, mesaj) {
  let kutu = alan.parentElement.querySelector(".field-warn");
  if (!mesaj) {
    if (kutu) kutu.remove();
    return;
  }
  if (!kutu) {
    kutu = document.createElement("span");
    kutu.className = "field-warn";
    kutu.setAttribute("role", "alert");
    alan.insertAdjacentElement("afterend", kutu);
  }
  kutu.textContent = mesaj;
}

function initFileSizeGuard() {
  document.querySelectorAll('input[type="file"][data-max-mb]').forEach((alan) => {
    const sinirMb = Number(alan.dataset.maxMb);
    alan.addEventListener("change", () => {
      const dosya = alan.files[0];
      const buyuk = dosya && dosya.size > sinirMb * 1024 * 1024;
      const mesaj = buyuk
        ? `Dosya ${(dosya.size / 1048576).toFixed(1)} MB; en fazla ${sinirMb} MB yüklenebilir.`
        : "";
      alan.setCustomValidity(mesaj);
      uyariGoster(alan, mesaj);
    });
  });
}

function initPasswordMatch() {
  const tekrar = document.querySelector('input[name="password2"]');
  const sifre = tekrar && tekrar.form.querySelector('input[name="password"]');
  if (!sifre) return;

  function denetle() {
    const mesaj = tekrar.value && tekrar.value !== sifre.value ? "Şifreler eşleşmiyor." : "";
    tekrar.setCustomValidity(mesaj);
    uyariGoster(tekrar, mesaj);
  }
  sifre.addEventListener("input", denetle);
  tekrar.addEventListener("input", denetle);
}

function notUyarisi(deger) {
  if (!deger.trim()) return "";
  const sayi = Number(deger.replace(",", "."));
  if (Number.isNaN(sayi)) return "Not sayı olmalı (örn. 3,45).";
  if (sayi < 0 || sayi > 100) return "Not 0–4 (veya 100'lük sistemde 0–100) aralığında olmalı.";
  return "";
}

function initCvRowWarnings() {
  const form = document.querySelector("[data-guard-unsaved]");
  if (!form) return;

  form.addEventListener("input", (e) => {
    const alan = e.target;
    if (alan.name === "edu_gpa[]") {
      uyariGoster(alan, notUyarisi(alan.value));
    } else if (alan.name === "edu_start_year[]" || alan.name === "edu_end_year[]") {
      const satir = alan.closest("[data-dynamic-row]");
      const bas = satir.querySelector('[name="edu_start_year[]"]');
      const bit = satir.querySelector('[name="edu_end_year[]"]');
      const ters = bas.value && bit.value && Number(bit.value) < Number(bas.value);
      uyariGoster(bit, ters ? "Bitiş yılı başlangıç yılından önce olamaz." : "");
    }
  });
}

/* --------------------------------------------------------------------------
   Canlı profil doluluğu (CV formu)

   Öğrenci yazdıkça doluluk yüzdesi tarayıcıda yeniden hesaplanır. Kural
   sunucudaki User.profile_completion() ile birebir aynıdır; kayıt sonrası
   panelde görülen yüzde ile burada görülen tutmalı. Bir satır, sunucunun
   kaydettiği gibi yalnızca zorunlu alanı doluysa sayılır.
   -------------------------------------------------------------------------- */

function doluMu(form, ad) {
  const alan = form.querySelector(`[name="${ad}"]`);
  return Boolean(alan && alan.value.trim());
}

function satirVarMi(form, ad) {
  return Array.from(form.querySelectorAll(`[name="${ad}[]"]`)).some((a) => a.value.trim());
}

function profilDolulugu(form, transkriptYuklu) {
  let puan = 0;
  if (["full_name", "department", "phone", "summary"].every((ad) => doluMu(form, ad))) puan += 25;
  if (satirVarMi(form, "edu_school")) puan += 25;

  const kaldir = form.querySelector('[name="remove_transcript"]');
  const yeniDosya = form.querySelector('[name="transcript"]');
  const transkript = (transkriptYuklu && !(kaldir && kaldir.checked)) ||
                     Boolean(yeniDosya && yeniDosya.files.length);
  if (transkript) puan += 20;

  if (satirVarMi(form, "exp_company") || satirVarMi(form, "proj_title")) puan += 15;
  if (satirVarMi(form, "cert_name")) puan += 15;
  return Math.min(puan, 100);
}

function initLiveCompletion() {
  const gosterge = document.querySelector("[data-live-completion]");
  const form = gosterge && gosterge.closest("article").querySelector("form");
  if (!form) return;

  const transkriptYuklu = gosterge.dataset.hasTranscript === "1";
  const meter = gosterge.querySelector(".meter");
  const dolgu = gosterge.querySelector(".meter-fill");
  const deger = gosterge.querySelector("[data-live-value]");

  function guncelle() {
    const yuzde = profilDolulugu(form, transkriptYuklu);
    dolgu.style.width = yuzde + "%";
    deger.textContent = "%" + yuzde;
    // Renk eşikleri panel ve listelerdekiyle aynı: 85 eksiksiz sayılır
    meter.classList.toggle("is-high", yuzde >= 85);
    meter.classList.toggle("is-mid", yuzde >= 50 && yuzde < 85);
  }

  form.addEventListener("input", guncelle);
  form.addEventListener("change", guncelle);
  // Satır silme "input" olayı üretmez; tıklamadan sonra yeniden hesapla
  form.addEventListener("click", (e) => {
    if (e.target.closest("[data-row-remove]")) setTimeout(guncelle, 0);
  });
  guncelle();
}

/* --------------------------------------------------------------------------
   Anlık arama (tablolar)

   data-live-search="tablo-id" olan bir arama kutusu, yazıldıkça o tablonun
   satırlarını sayfayı yenilemeden süzer. Sunucu tarafı arama (Filtrele
   butonu) yerinde kalır; JavaScript kapalıysa form eskisi gibi çalışır.
   -------------------------------------------------------------------------- */

function normalize(metin) {
  // Türkçe büyük/küçük harf: "İ".toLowerCase() "i̇" verir, tr yereliyle düzelir
  return metin.toLocaleLowerCase("tr").normalize("NFD").replace(/[̀-ͯ]/g, "");
}

function initLiveSearch() {
  document.querySelectorAll("[data-live-search]").forEach((kutu) => {
    const tablo = document.getElementById(kutu.dataset.liveSearch);
    const sayac = document.querySelector("[data-live-count]");
    if (!tablo) return;
    const satirlar = Array.from(tablo.tBodies[0].rows);

    kutu.addEventListener("input", () => {
      const aranan = normalize(kutu.value.trim());
      let gorunen = 0;
      satirlar.forEach((satir) => {
        const eslesti = !aranan || normalize(satir.textContent).includes(aranan);
        satir.hidden = !eslesti;
        if (eslesti) gorunen += 1;
      });
      if (sayac) sayac.textContent = gorunen;
    });
  });
}

/* Geri alinmasi zahmetli islemler icin onay sorar.
   Formda data-confirm="soru" olmasi yeterli; satir ici JavaScript yok. */
function initConfirmForms() {
  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });
}

function initMobileMenu() {
  const btn = document.getElementById("mobile-menu-btn");
  const menu = document.getElementById("mobile-menu");
  const backdrop = document.getElementById("mobile-backdrop");
  const closeBtn = document.getElementById("mobile-menu-close");
  if (!btn || !menu || !backdrop) return;

  function setOpen(open) {
    menu.classList.toggle("is-open", open);
    backdrop.classList.toggle("is-open", open);
    btn.setAttribute("aria-expanded", String(open));

    // Çekmece açıkken arkadaki sayfa kaymasın
    document.body.style.overflow = open ? "hidden" : "";

    // Açılınca odağı çekmecenin içine al, kapanınca butona geri ver
    if (open) {
      (closeBtn || menu.querySelector("a") || menu).focus();
    } else {
      btn.focus();
    }
  }

  btn.addEventListener("click", () => setOpen(!menu.classList.contains("is-open")));
  backdrop.addEventListener("click", () => setOpen(false));
  if (closeBtn) closeBtn.addEventListener("click", () => setOpen(false));

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && menu.classList.contains("is-open")) setOpen(false);
  });

  // Pencere masaüstü genişliğine çıkarsa çekmece açık kalmasın
  window.addEventListener("resize", () => {
    if (window.innerWidth > 860 && menu.classList.contains("is-open")) setOpen(false);
  });
}

function initTabs() {
  const tabButtons = Array.from(document.querySelectorAll("[data-tab-target]"));
  const tabPanels = document.querySelectorAll("[data-tab-panel]");
  if (!tabButtons.length) return;

  function activate(btn) {
    const target = btn.getAttribute("data-tab-target");

    // Görünüm tamamen CSS'te: tek bir "is-active" sınıfı taşınır.
    tabButtons.forEach((b) => {
      b.classList.remove("is-active");
      b.setAttribute("aria-selected", "false");
      b.setAttribute("tabindex", "-1");
    });
    btn.classList.add("is-active");
    btn.setAttribute("aria-selected", "true");
    btn.setAttribute("tabindex", "0");

    tabPanels.forEach((p) => p.classList.add("hidden"));
    const activePanel = document.querySelector(`[data-tab-panel="${target}"]`);
    if (activePanel) activePanel.classList.remove("hidden");
  }

  tabButtons.forEach((btn, i) => {
    btn.setAttribute("tabindex", btn.classList.contains("is-active") ? "0" : "-1");
    btn.addEventListener("click", () => activate(btn));

    // Sekmelerde ok tuşlarıyla gezinme (WAI-ARIA sekme deseni).
    // Tek tek Tab'layarak değil, yön tuşlarıyla dolaşılır.
    btn.addEventListener("keydown", (e) => {
      let next = null;
      if (e.key === "ArrowRight") next = tabButtons[(i + 1) % tabButtons.length];
      else if (e.key === "ArrowLeft") next = tabButtons[(i - 1 + tabButtons.length) % tabButtons.length];
      else if (e.key === "Home") next = tabButtons[0];
      else if (e.key === "End") next = tabButtons[tabButtons.length - 1];
      if (!next) return;
      e.preventDefault();
      activate(next);
      next.focus();
    });
  });
}

function addRow(containerId, templateId) {
  const container = document.getElementById(containerId);
  const template = document.getElementById(templateId);
  if (!container || !template) return;
  const clone = template.content.cloneNode(true);
  container.appendChild(clone);
}

function initDynamicRows() {
  document.querySelectorAll("[data-row-add]").forEach((btn) => {
    const containerId = btn.getAttribute("data-row-add");
    const templateId = btn.getAttribute("data-row-template");

    btn.addEventListener("click", () => {
      addRow(containerId, templateId);
      markDirty();
    });

    // Sayfa ilk açıldığında satır yoksa (yeni öğrenci) bir tane boş satır ekle
    const container = document.getElementById(containerId);
    if (container && container.children.length === 0) {
      addRow(containerId, templateId);
    }
  });

  // Silme butonlarını delegasyonla dinle (sonradan eklenen satırlar dahil)
  document.body.addEventListener("click", (e) => {
    const removeBtn = e.target.closest("[data-row-remove]");
    if (removeBtn) {
      const row = removeBtn.closest("[data-dynamic-row]");
      if (row) {
        row.remove();
        markDirty();
      }
    }
  });
}

/* --------------------------------------------------------------------------
   Kaydedilmemiş değişiklik koruması

   CV formu beş sekmeye yayılıyor ve tek bir Kaydet butonu var. Sekmeleri
   doldurup kaydetmeden sayfadan çıkmak bütün emeği siliyordu; artık
   tarayıcı onay soruyor. Satır ekleme/silme de değişiklik sayılır, çünkü
   bunlar "input" olayı üretmiyor.
   -------------------------------------------------------------------------- */

let formDirty = false;

function markDirty() {
  formDirty = true;
}

function initUnsavedGuard() {
  const form = document.querySelector("[data-guard-unsaved]");
  if (!form) return;

  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);

  // Gönderim sırasında uyarı çıkmasın
  form.addEventListener("submit", () => {
    formDirty = false;
  });

  window.addEventListener("beforeunload", (e) => {
    if (!formDirty) return;
    e.preventDefault();
    e.returnValue = "";
  });
}
