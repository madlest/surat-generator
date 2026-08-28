// Dashboard: daftar jenis surat dalam bentuk kartu, dikelompokkan per unit.
//
// Modul ini sengaja tidak mengimpor form.js atau admin.js. Aksi saat kartu
// diklik disuntikkan lewat initDashboard() dari app.js, supaya tidak terjadi
// impor melingkar (admin.js sendiri memanggil loadDashboard setelah menyimpan).
//
// Sejak Stage 4: tiap kartu membawa unit_slug-nya. Untuk admin biasa hanya ada
// satu unit, jadi heading unit tidak ditampilkan (UI-nya sama seperti dulu);
// untuk superadmin yang melihat banyak unit, kartu dikelompokkan dengan heading.

import { setText } from "./helpers.js";

let handlers = {
  onSelectType: () => {},
  onAddNew: () => {},
  onEditType: () => {},
};

export function initDashboard(nextHandlers) {
  handlers = { ...handlers, ...nextHandlers };
}

const dashboardGrid = document.getElementById("dashboard-grid");

export async function loadDashboard() {
  dashboardGrid.innerHTML =
    '<p class="dashboard-loading">Memuat jenis surat&hellip;</p>';
  try {
    const res = await fetch("/admin/letter-types");
    if (!res.ok) throw new Error("Gagal memuat daftar jenis surat.");
    const types = await res.json();
    renderDashboard(types);
  } catch (err) {
    dashboardGrid.innerHTML = "";
    dashboardGrid.appendChild(
      setText(document.createElement("p"), err.message),
    );
    dashboardGrid.lastChild.className = "dashboard-error";
  }
}

function makeCard(t) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "type-card";

  const mark = document.createElement("span");
  mark.className = "type-card-mark";
  mark.textContent = (t.name.trim().charAt(0) || "?").toUpperCase();

  const name = document.createElement("span");
  name.className = "type-card-name";
  name.textContent = t.name;

  const slug = document.createElement("span");
  slug.className = "type-card-slug";
  slug.textContent = t.slug;

  card.append(mark, name, slug);
  card.addEventListener("click", () => handlers.onSelectType(t.unit_slug, t.slug));

  // Tombol ubah diletakkan di dalam kartu, jadi kliknya perlu dihentikan
  // agar tidak ikut memicu pembukaan form seperti klik kartu biasa.
  const editBtn = document.createElement("button");
  editBtn.type = "button";
  editBtn.className = "type-card-edit";
  editBtn.title = `Ubah "${t.name}"`;
  editBtn.setAttribute("aria-label", `Ubah jenis surat ${t.name}`);
  editBtn.textContent = "✎";
  editBtn.addEventListener("click", (event) => {
    event.stopPropagation();
    handlers.onEditType(t.unit_slug, t.slug);
  });
  card.appendChild(editBtn);

  return card;
}

function makeAddCard() {
  const addCard = document.createElement("button");
  addCard.type = "button";
  addCard.className = "type-card add-new";
  addCard.innerHTML = '<span class="plus">+</span>';
  addCard.appendChild(
    setText(document.createElement("span"), "Tambah Jenis Surat Baru"),
  );
  addCard.addEventListener("click", () => handlers.onAddNew());
  return addCard;
}

function renderDashboard(types) {
  dashboardGrid.innerHTML = "";

  if (types.length === 0) {
    const empty = setText(
      document.createElement("p"),
      "Belum ada jenis surat. Tambahkan yang pertama.",
    );
    empty.className = "dashboard-empty";
    dashboardGrid.appendChild(empty);
    dashboardGrid.appendChild(wrapGrid([makeAddCard()]));
    return;
  }

  // Kelompokkan per unit, mempertahankan urutan kemunculan dari server.
  const groups = new Map();
  types.forEach((t) => {
    if (!groups.has(t.unit_slug)) {
      groups.set(t.unit_slug, { name: t.unit_name, items: [] });
    }
    groups.get(t.unit_slug).items.push(t);
  });

  const showHeadings = groups.size > 1;

  groups.forEach((group) => {
    const cards = group.items.map(makeCard);
    if (showHeadings) {
      const heading = setText(document.createElement("h2"), group.name);
      heading.className = "dashboard-unit-heading";
      dashboardGrid.appendChild(heading);
      dashboardGrid.appendChild(wrapGrid(cards));
    } else {
      // Satu unit saja: kartu "tambah" ikut di grid yang sama, persis seperti
      // tampilan sebelum ada pengelompokan.
      cards.push(makeAddCard());
      dashboardGrid.appendChild(wrapGrid(cards));
    }
  });

  if (showHeadings) {
    // Untuk superadmin, "tambah" berdiri sendiri di bawah — wizard yang akan
    // menanyakan unit tujuannya.
    dashboardGrid.appendChild(wrapGrid([makeAddCard()]));
  }
}

function wrapGrid(cards) {
  const grid = document.createElement("div");
  grid.className = "dashboard-grid-inner";
  cards.forEach((c) => grid.appendChild(c));
  return grid;
}
