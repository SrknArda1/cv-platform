/* Yönetici paneli: yetkinlik dağılımının ABC (Pareto) analizi.

   Akış: sayfa açılır -> fetch ile /api/v1/yetkinlikler JSON'u çekilir ->
   kümülatif yüzde ve ABC sınıfı tarayıcıda hesaplanır -> Chart.js ile
   çubuk (öğrenci sayısı) + çizgi (kümülatif %) grafiği çizilir.

   ABC kuralı (stok yönetimindeki klasik kural): yetkinlikler en sık
   görülenden başlayarak sıralanır; kümülatif pay %80'e kadar olanlar A,
   %95'e kadar olanlar B, kalanlar C sınıfıdır. */

document.addEventListener("DOMContentLoaded", () => {
  const bolum = document.getElementById("abc-analizi");
  if (!bolum) return;
  abcAnaliziYukle(bolum);
});

const ABC_SINIRLARI = { A: 80, B: 95 };
const GRAFIKTE_EN_COK = 15; // Uzun kuyruk grafiği okunmaz yapar

function abcSiniflandir(kayitlar) {
  // API zaten azalan sırada döner; yine de sıralamaya güvenmeyip sıralıyoruz.
  const sirali = [...kayitlar].sort((a, b) => b.student_count - a.student_count);
  const toplam = sirali.reduce((t, k) => t + k.student_count, 0);
  let kumulatif = 0;

  return sirali.map((k) => {
    kumulatif += k.student_count;
    const pay = toplam ? (kumulatif / toplam) * 100 : 0;
    // Sınıf, yetkinlik eklenMEDEN önceki paya göre verilir; yoksa en sık
    // yetkinlik tek başına %80'i aşarsa A yerine B olurdu.
    const onceki = pay - (toplam ? (k.student_count / toplam) * 100 : 0);
    const sinif = onceki < ABC_SINIRLARI.A ? "A" : onceki < ABC_SINIRLARI.B ? "B" : "C";
    return { ad: k.name, adet: k.student_count, kumulatif: Math.round(pay * 10) / 10, sinif };
  });
}

function cssRengi(ad) {
  return getComputedStyle(document.documentElement).getPropertyValue(ad).trim();
}

async function abcAnaliziYukle(bolum) {
  const ozet = document.getElementById("abc-ozet");

  let kayitlar;
  try {
    const yanit = await fetch(bolum.dataset.kaynak, { headers: { Accept: "application/json" } });
    if (!yanit.ok) throw new Error(`HTTP ${yanit.status}`);
    kayitlar = (await yanit.json()).data;
  } catch (hata) {
    ozet.textContent = "Yetkinlik verisi alınamadı (" + hata.message + "). Sayfayı yenileyin.";
    return;
  }

  if (!kayitlar.length) {
    ozet.textContent = "Henüz yetkinlik girmiş öğrenci yok.";
    return;
  }

  const sonuc = abcSiniflandir(kayitlar);
  const sinifSayisi = { A: 0, B: 0, C: 0 };
  sonuc.forEach((s) => { sinifSayisi[s.sinif] += 1; });

  const aSinifi = sonuc.filter((s) => s.sinif === "A").map((s) => s.ad);
  ozet.textContent =
    `${sonuc.length} farklı yetkinlik: A sınıfı ${sinifSayisi.A}, B ${sinifSayisi.B}, C ${sinifSayisi.C}. ` +
    `Bahsedilmelerin %80'ini oluşturan A sınıfı: ${aSinifi.join(", ")}.`;

  if (typeof Chart === "undefined") return; // Grafik kütüphanesi yüklenmediyse özet metni yeter

  const gosterilen = sonuc.slice(0, GRAFIKTE_EN_COK);
  const renk = { A: cssRengi("--accent"), B: cssRengi("--warn"), C: cssRengi("--ink-3") };

  new Chart(document.getElementById("abc-grafik"), {
    data: {
      labels: gosterilen.map((s) => s.ad),
      datasets: [
        {
          type: "bar",
          label: "Öğrenci sayısı",
          data: gosterilen.map((s) => s.adet),
          backgroundColor: gosterilen.map((s) => renk[s.sinif]),
          yAxisID: "y",
          order: 2,
        },
        {
          type: "line",
          label: "Kümülatif %",
          data: gosterilen.map((s) => s.kumulatif),
          borderColor: cssRengi("--danger"),
          backgroundColor: cssRengi("--danger"),
          pointRadius: 3,
          tension: 0.2,
          yAxisID: "y2",
          order: 1,
        },
      ],
    },
    options: {
      maintainAspectRatio: false,
      plugins: {
        tooltip: {
          callbacks: {
            afterLabel: (ctx) => (ctx.datasetIndex === 0 ? `Sınıf: ${gosterilen[ctx.dataIndex].sinif}` : ""),
          },
        },
      },
      scales: {
        y: { beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Öğrenci" } },
        y2: {
          position: "right", min: 0, max: 100,
          grid: { drawOnChartArea: false },
          ticks: { callback: (v) => v + "%" },
        },
      },
    },
  });
}
