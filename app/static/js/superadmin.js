// Panel khusus superadmin: kelola daftar unit dan undang/nonaktifkan admin.
//
// Semua endpoint di sini dijaga require_superadmin di backend — modul ini
// hanya dimuat kalau tombolnya diklik, dan tombolnya sendiri disembunyikan
// auth.js untuk non-superadmin. Jadi ini kemudahan UI, bukan pengaman.

import { showView } from "./views.js";
import { getCurrentUser } from "./auth.js";

const ROLE_LABEL = {
  superadmin: "Superadmin",
  admin: "Admin",
};

// Sama persis dengan slugify di admin.js — sengaja tidak diekstrak ke modul
// bersama karena aturannya bisa saja beda kelak (slug unit vs slug jenis surat).
function slugify(text) {
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

let unitSlugManuallyEdited = false;
let unitsCache = [];

function setStatus(el, kind, message) {
  el.className = kind ? `status show ${kind}` : "status";
  el.textContent = message || "";
}

function detailOf(data, fallback) {
  return data && typeof data.detail === "string" ? data.detail : fallback;
}

function mutedRow(text) {
  const p = document.createElement("p");
  p.className = "sa-empty";
  p.textContent = text;
  return p;
}

// --- Unit ------------------------------------------------------------------

async function loadUnits() {
  const listEl = document.getElementById("unit-list");
  listEl.innerHTML = "";
  listEl.appendChild(mutedRow("Memuat daftar unit…"));
  try {
    const res = await fetch("/admin/units");
    if (!res.ok) throw new Error("Gagal memuat daftar unit.");
    unitsCache = await res.json();
    renderUnits(unitsCache);
    populateInviteUnitOptions(unitsCache);
  } catch (err) {
    listEl.innerHTML = "";
    listEl.appendChild(mutedRow(err.message));
  }
}

function mkAction(label, handler) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "sa-row-action";
  btn.textContent = label;
  btn.addEventListener("click", handler);
  return btn;
}

function renderUnits(units) {
  const listEl = document.getElementById("unit-list");
  listEl.innerHTML = "";
  if (units.length === 0) {
    listEl.appendChild(mutedRow("Belum ada unit."));
    return;
  }
  units.forEach((u) => listEl.appendChild(unitRow(u)));
}

function unitRow(u) {
  const row = document.createElement("div");
  row.className = "sa-row";

  const main = document.createElement("div");
  main.className = "sa-row-main";
  const title = document.createElement("span");
  title.className = "sa-row-title";
  title.textContent = u.name;
  const sub = document.createElement("span");
  sub.className = "sa-row-sub";
  sub.textContent = u.slug;
  main.append(title, sub);

  const actions = document.createElement("div");
  actions.className = "sa-row-actions";
  actions.append(
    mkAction("Ubah nama", () => startRenameUnit(u, row)),
    mkAction("Hapus", () => confirmDeleteUnit(u, row)),
  );
  actions.lastChild.classList.add("sa-row-action-danger");

  row.append(main, actions);
  return row;
}

// Baris diganti isinya jadi form inline; batal / selesai memuat ulang seluruh
// daftar (lebih sederhana daripada menyusun ulang baris satu-satu).
function startRenameUnit(u, row) {
  row.innerHTML = "";
  row.classList.add("sa-row-editing");

  const input = document.createElement("input");
  input.type = "text";
  input.className = "sa-inline-input";
  input.value = u.name;
  input.setAttribute("aria-label", `Nama baru untuk unit ${u.slug}`);

  const save = mkAction("Simpan", async () => {
    const name = input.value.trim();
    if (!name) {
      input.focus();
      return;
    }
    save.disabled = true;
    try {
      const res = await fetch(`/admin/units/${u.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, "Gagal mengubah nama unit."));
      setStatus(document.getElementById("unit-status"), "success", `Nama unit diubah jadi "${data.name}".`);
      await loadUnits();
    } catch (err) {
      setStatus(document.getElementById("unit-status"), "error", err.message);
      save.disabled = false;
    }
  });
  const cancel = mkAction("Batal", () => loadUnits());

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") save.click();
    if (e.key === "Escape") cancel.click();
  });

  row.append(input, save, cancel);
  input.focus();
  input.select();
}

function confirmDeleteUnit(u, row) {
  row.innerHTML = "";
  row.classList.add("sa-row-editing");

  const label = document.createElement("span");
  label.className = "sa-row-sub";
  label.textContent = `Hapus unit "${u.name}" (${u.slug})?`;

  const yes = mkAction("Ya, hapus", async () => {
    yes.disabled = true;
    try {
      const res = await fetch(`/admin/units/${u.id}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(detailOf(data, "Gagal menghapus unit."));
      setStatus(document.getElementById("unit-status"), "success", `Unit "${u.name}" dihapus.`);
    } catch (err) {
      setStatus(document.getElementById("unit-status"), "error", err.message);
    }
    await loadUnits();
  });
  yes.classList.add("sa-row-action-danger");
  const cancel = mkAction("Batal", () => loadUnits());

  row.append(label, yes, cancel);
}

async function submitUnit() {
  const statusEl = document.getElementById("unit-status");
  const nameEl = document.getElementById("unit-name-input");
  const slugEl = document.getElementById("unit-slug-input");
  const name = nameEl.value.trim();
  const slug = slugEl.value.trim();

  if (!name || !slug) {
    setStatus(statusEl, "error", "Nama dan slug unit wajib diisi.");
    return;
  }

  setStatus(statusEl, "loading", "Menyimpan unit…");
  try {
    const res = await fetch("/admin/units", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, slug }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(detailOf(data, "Gagal menyimpan unit."));

    setStatus(statusEl, "success", `Unit "${data.name}" ditambahkan.`);
    nameEl.value = "";
    slugEl.value = "";
    unitSlugManuallyEdited = false;
    await loadUnits();
  } catch (err) {
    setStatus(statusEl, "error", err.message);
  }
}

// --- User / Admin --------------------------------------------------------

async function loadUsers() {
  const listEl = document.getElementById("user-list");
  listEl.innerHTML = "";
  listEl.appendChild(mutedRow("Memuat daftar admin…"));
  try {
    const res = await fetch("/admin/users");
    if (!res.ok) throw new Error("Gagal memuat daftar admin.");
    renderUsers(await res.json());
  } catch (err) {
    listEl.innerHTML = "";
    listEl.appendChild(mutedRow(err.message));
  }
}

function formatLastLogin(value) {
  if (!value) return "Belum pernah login";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Belum pernah login";
  return `Login terakhir ${d.toLocaleDateString("id-ID")}`;
}

function renderUsers(users) {
  const listEl = document.getElementById("user-list");
  listEl.innerHTML = "";
  const me = getCurrentUser();

  if (users.length === 0) {
    listEl.appendChild(mutedRow("Belum ada admin diundang."));
    return;
  }

  users.forEach((u) => {
    const isSelf = me && u.email === me.email;

    const row = document.createElement("div");
    row.className = "sa-row" + (u.is_active ? "" : " sa-row-inactive");

    const main = document.createElement("div");
    main.className = "sa-row-main";

    const title = document.createElement("span");
    title.className = "sa-row-title";
    title.textContent = u.name || u.email;

    const sub = document.createElement("span");
    sub.className = "sa-row-sub";
    const unitPart = u.role === "superadmin" ? "semua unit" : u.unit_name || "tanpa unit";
    const bits = [ROLE_LABEL[u.role] || u.role, unitPart, formatLastLogin(u.last_login_at)];
    if (u.name) bits.unshift(u.email);
    sub.textContent = bits.join("  ·  ");

    main.append(title, sub);
    row.appendChild(main);

    const actions = document.createElement("div");
    actions.className = "sa-row-actions";

    if (!u.is_active) {
      const badge = document.createElement("span");
      badge.className = "sa-badge sa-badge-off";
      badge.textContent = "Nonaktif";
      actions.appendChild(badge);
    }

    if (isSelf) {
      const badge = document.createElement("span");
      badge.className = "sa-badge";
      badge.textContent = "Anda";
      actions.appendChild(badge);
    } else {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "sa-row-action";
      btn.textContent = u.is_active ? "Nonaktifkan" : "Aktifkan";
      btn.addEventListener("click", () =>
        patchUser(u.id, u.is_active ? "deactivate" : "reactivate"),
      );
      actions.appendChild(btn);
    }

    row.appendChild(actions);
    listEl.appendChild(row);
  });
}

async function patchUser(userId, action) {
  const statusEl = document.getElementById("invite-status");
  setStatus(statusEl, "loading", "Menyimpan…");
  try {
    const res = await fetch(`/admin/users/${userId}/${action}`, { method: "PATCH" });
    const data = await res.json();
    if (!res.ok) throw new Error(detailOf(data, "Gagal mengubah status admin."));
    setStatus(statusEl, "", "");
    await loadUsers();
  } catch (err) {
    setStatus(statusEl, "error", err.message);
  }
}

function populateInviteUnitOptions(units) {
  const sel = document.getElementById("invite-unit-select");
  sel.innerHTML = "";
  if (units.length === 0) {
    sel.appendChild(new Option("— belum ada unit —", ""));
    sel.disabled = true;
    return;
  }
  sel.disabled = false;
  units.forEach((u) => sel.appendChild(new Option(`${u.name} (${u.slug})`, String(u.id))));
}

// Field unit hanya relevan saat mengundang admin biasa. Superadmin tidak
// terikat satu unit, jadi field-nya disembunyikan (dan backend menolak kalau
// unit_id tetap dikirim untuk peran superadmin).
function syncInviteUnitVisibility() {
  const role = document.getElementById("invite-role-select").value;
  document.getElementById("invite-unit-field").hidden = role !== "admin";
}

async function submitInvite() {
  const statusEl = document.getElementById("invite-status");
  const emailEl = document.getElementById("invite-email-input");
  const role = document.getElementById("invite-role-select").value;
  const email = emailEl.value.trim();

  if (!email) {
    setStatus(statusEl, "error", "Email wajib diisi.");
    return;
  }

  const payload = { email, role };
  if (role === "admin") {
    const unitId = document.getElementById("invite-unit-select").value;
    if (!unitId) {
      setStatus(statusEl, "error", "Pilih unit untuk admin biasa. Tambahkan unit dulu kalau belum ada.");
      return;
    }
    payload.unit_id = Number(unitId);
  }

  setStatus(statusEl, "loading", "Mengirim undangan…");
  try {
    const res = await fetch("/admin/users/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(detailOf(data, "Gagal mengundang."));

    setStatus(
      statusEl,
      "success",
      `Undangan untuk ${data.email} dibuat. Ia bisa langsung login lewat Google.`,
    );
    emailEl.value = "";
    await loadUsers();
  } catch (err) {
    setStatus(statusEl, "error", err.message);
  }
}

// --- Wiring -------------------------------------------------------------

export function initSuperadmin() {
  document.getElementById("unit-add-btn").addEventListener("click", submitUnit);

  const unitName = document.getElementById("unit-name-input");
  const unitSlug = document.getElementById("unit-slug-input");
  unitName.addEventListener("input", (e) => {
    if (!unitSlugManuallyEdited) unitSlug.value = slugify(e.target.value);
  });
  unitSlug.addEventListener("input", () => {
    unitSlugManuallyEdited = true;
  });

  document.getElementById("invite-role-select").addEventListener("change", syncInviteUnitVisibility);
  document.getElementById("invite-btn").addEventListener("click", submitInvite);
  syncInviteUnitVisibility();
}

export function openSuperadminPanel() {
  showView("view-superadmin");
  document.getElementById("unit-status").className = "status";
  document.getElementById("invite-status").className = "status";
  loadUnits();
  loadUsers();
}
