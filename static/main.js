document.addEventListener("DOMContentLoaded", () => {
  initMobileMenu();
  initTabs();
  initDynamicRows();
});

function initMobileMenu() {
  const btn = document.getElementById("mobile-menu-btn");
  const menu = document.getElementById("mobile-menu");
  if (btn && menu) {
    btn.addEventListener("click", () => menu.classList.toggle("hidden"));
  }
}

function initTabs() {
  const tabButtons = document.querySelectorAll("[data-tab-target]");
  const tabPanels = document.querySelectorAll("[data-tab-panel]");
  if (!tabButtons.length) return;

  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.getAttribute("data-tab-target");

      tabButtons.forEach((b) => {
        b.classList.remove("active", "bg-indigo-600", "text-white");
        b.classList.add("bg-white", "text-slate-600");
      });
      btn.classList.add("active", "bg-indigo-600", "text-white");
      btn.classList.remove("bg-white", "text-slate-600");

      tabPanels.forEach((p) => p.classList.add("hidden"));
      const activePanel = document.querySelector(`[data-tab-panel="${target}"]`);
      if (activePanel) activePanel.classList.remove("hidden");
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

    btn.addEventListener("click", () => addRow(containerId, templateId));

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
      if (row) row.remove();
    }
  });
}
