document.addEventListener("DOMContentLoaded", () => {
  initMobileMenu();
  initTabs();
  initDynamicRows();
  initUnsavedGuard();
});

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
