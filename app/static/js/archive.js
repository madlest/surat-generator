// Halaman arsip: jenis surat yang sudah dihapus, beserta aksi memulihkan dan
// menghapusnya untuk selamanya.
//
// Sama seperti dashboard.js, modul ini tidak mengimpor modul tampilan lain.
// Aksi setelah pemulihan disuntikkan dari app.js supaya tidak terjadi impor
// melingkar.

import { setText } from "./helpers.js";

const archiveList = document.getElementById("archive-list");

let handlers = {
  onRestored: () => {},
};

export function initArchive(nextHandlers) {
  handlers = { ...handlers, ...nextHandlers };
}

function formatTanggalHapus(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const tanggal = String(d.getDate()).padStart(2, "0");
  const bulan = String(d.getMonth() + 1).padStart(2, "0");
  return `${tanggal}-${bulan}-${d.getFullYear()}`;
}

export async function loadArchive() {
  archiveList.innerHTML =
    '<p class="dashboard-loading">Memuat arsip&hellip;</p>';
  try {
    const res = await fetch("/admin/letter-types/archived");
    if (!res.ok) throw new Error("Gagal memuat arsip.");
    renderArchive(await res.json());
  } catch (err) {
    archiveList.innerHTML = "";
    const p = setText(document.createElement("p"), err.message);
    p.className = "dashboard-error";
    archiveList.appendChild(p);
  }
}

function renderArchive(items) {
  archiveList.innerHTML = "";

  if (items.length === 0) {
    const kosong = setText(
      document.createElement("p"),
      "Arsip kosong. Jenis surat yang dihapus akan muncul di sini.",
    );
    kosong.className = "dashboard-empty";
    archiveList.appendChild(kosong);
    return;
  }

  // Kelompokkan per unit — heading hanya kalau ada lebih dari satu unit
  // (superadmin). Konsisten dengan dashboard.
  const groups = new Map();
  items.forEach((item) => {
    if (!groups.has(item.unit_slug)) {
      groups.set(item.unit_slug, { name: item.unit_name, items: [] });
    }
    groups.get(item.unit_slug).items.push(item);
  });
  const showHeadings = groups.size > 1;

  groups.forEach((group) => {
    if (showHeadings) {
      const heading = setText(document.createElement("h2"), group.name);
      heading.className = "dashboard-unit-heading";
      archiveList.appendChild(heading);
    }
    group.items.forEach((item) => renderArchiveRow(item));
  });
}

function renderArchiveRow(item) {
  const row = document.createElement("div");
  row.className = "archive-row";

  const info = document.createElement("div");
  info.className = "archive-info";
  const nama = document.createElement("span");
  nama.className = "archive-name";
  nama.textContent = item.name;
  const meta = document.createElement("span");
  meta.className = "archive-meta";
  const tanggal = formatTanggalHapus(item.deleted_at);
  meta.textContent = tanggal
    ? `${item.slug} · dihapus ${tanggal}`
    : item.slug;
  info.append(nama, meta);

  const aksi = document.createElement("div");
  aksi.className = "archive-actions";

  const restoreBtn = setText(document.createElement("button"), "Pulihkan");
  restoreBtn.type = "button";
  restoreBtn.className = "archive-restore-btn";
  restoreBtn.addEventListener("click", () => pulihkan(item, row));

  const purgeBtn = setText(document.createElement("button"), "Hapus permanen");
  purgeBtn.type = "button";
  purgeBtn.className = "archive-purge-btn";
  purgeBtn.addEventListener("click", () => bukaKonfirmasiHapus(item, row));

  aksi.append(restoreBtn, purgeBtn);
  row.append(info, aksi);
  archiveList.appendChild(row);
}

function tampilkanPesan(row, tipe, teks) {
  row.querySelector(".archive-status")?.remove();
  const status = setText(document.createElement("div"), teks);
  status.className = `status show ${tipe} archive-status`;
  row.appendChild(status);
}

async function pulihkan(item, row) {
  try {
    const res = await fetch(
      `/admin/letter-types/archived/${encodeURIComponent(item.slug)}/restore` +
        `?unit_slug=${encodeURIComponent(item.unit_slug)}`,
      { method: "POST" },
    );
    const data = await res.json();
    if (!res.ok)
      throw new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Gagal memulihkan jenis surat.",
      );

    tampilkanPesan(row, "success", `"${item.name}" telah dipulihkan.`);
    setTimeout(() => {
      loadArchive();
      handlers.onRestored();
    }, 1000);
  } catch (err) {
    tampilkanPesan(row, "error", err.message);
  }
}

function bukaKonfirmasiHapus(item, row) {
  // Konfirmasi dimunculkan di baris itu sendiri, bukan lewat dialog, supaya
  // jelas jenis surat mana yang sedang dihapus.
  if (row.querySelector(".archive-confirm")) return;

  const kotak = document.createElement("div");
  kotak.className = "archive-confirm";

  const label = document.createElement("label");
  const inputId = `purge-confirm-${item.slug}`;
  label.setAttribute("for", inputId);
  label.append(
    document.createTextNode("Ketik "),
    Object.assign(document.createElement("strong"), { textContent: item.name }),
    document.createTextNode(" untuk menghapus selamanya"),
  );

  const input = document.createElement("input");
  input.type = "text";
  input.id = inputId;
  input.autocomplete = "off";

  const tombol = setText(document.createElement("button"), "Hapus Selamanya");
  tombol.type = "button";
  tombol.className = "danger-btn";
  tombol.disabled = true;

  input.addEventListener("input", () => {
    tombol.disabled = input.value.trim() !== item.name;
  });

  tombol.addEventListener("click", async () => {
    tombol.disabled = true;
    try {
      const res = await fetch(
        `/admin/letter-types/archived/${encodeURIComponent(item.slug)}/purge` +
          `?confirm_name=${encodeURIComponent(input.value.trim())}` +
          `&unit_slug=${encodeURIComponent(item.unit_slug)}`,
        { method: "DELETE" },
      );
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal menghapus jenis surat.",
        );

      kotak.remove();
      tampilkanPesan(
        row,
        "success",
        `"${item.name}" dihapus selamanya beserta templatnya.`,
      );
      setTimeout(loadArchive, 1200);
    } catch (err) {
      tampilkanPesan(row, "error", err.message);
      tombol.disabled = false;
    }
  });

  kotak.append(label, input, tombol);
  row.appendChild(kotak);
  input.focus();
}