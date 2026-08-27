// Wizard admin, dipakai untuk dua hal: menambah jenis surat baru dan menyunting
// yang sudah ada. Alurnya sama — unggah template untuk mendeteksi variabelnya,
// lalu atur label, tipe, dan level tiap field.
//
// Bedanya saat menyunting: template boleh tidak diganti (konfigurasi field yang
// tersimpan langsung ditampilkan), dan kiriman memakai PUT alih-alih POST.

import { setText } from "./helpers.js";
import { showView } from "./views.js";
import { loadDashboard } from "./dashboard.js";

let selectedTemplateFile = null;
let detectedVariables = [];
let slugManuallyEdited = false;
// null saat menambah jenis surat baru; berisi slug asal saat menyunting.
// Slug asal disimpan terpisah dari isian slug karena keduanya bisa berbeda:
// yang asal dipakai sebagai alamat endpoint, yang di isian adalah slug tujuan.
let editingSlug = null;
// Nama jenis surat yang sedang disunting, dipakai sebagai pembanding saat
// admin mengetik ulang nama untuk mengonfirmasi penghapusan.
let editingName = "";

function slugify(text) {
  return text
    .toString()
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function resetAdminWizard() {
  selectedTemplateFile = null;
  detectedVariables = [];
  slugManuallyEdited = false;
  editingSlug = null;
  editingName = "";
  document.getElementById("admin-delete-confirm").value = "";
  document.getElementById("admin-delete-btn").disabled = true;
  document.getElementById("admin-delete-status").className = "status";
  document.getElementById("admin-delete-status").textContent = "";
  document.getElementById("admin-template-file").value = "";
  document.getElementById("admin-name").value = "";
  document.getElementById("admin-slug").value = "";
  document.getElementById("admin-fields-list").innerHTML = "";
  document.getElementById("admin-no-vars-note").style.display = "none";
  document.getElementById("admin-step-2").style.display = "none";
  document.getElementById("admin-inspect-status").className = "status";
  document.getElementById("admin-inspect-status").textContent = "";
  document.getElementById("admin-submit-status").className = "status";
  document.getElementById("admin-submit-status").textContent = "";
}

/**
 * Sesuaikan judul, label, dan tombol mengikuti mode yang sedang aktif.
 * Semua teks yang berbeda antara "tambah" dan "ubah" dikumpulkan di sini
 * supaya tidak tersebar di banyak tempat.
 */
function applyWizardMode(isEditing) {
  setText(
    document.getElementById("admin-title"),
    isEditing ? "Ubah Jenis Surat" : "Tambah Jenis Surat Baru",
  );
  setText(
    document.getElementById("admin-subtitle"),
    isEditing
      ? "Perbarui nama, slug, atau konfigurasi field. Template hanya perlu diunggah kalau memang mau diganti."
      : "Upload template docx, lalu atur field-nya. Tidak perlu kode.",
  );
  setText(
    document.getElementById("admin-template-label"),
    isEditing ? "Ganti Template (.docx) — opsional" : "File Template (.docx)",
  );
  setText(
    document.getElementById("admin-submit-label"),
    isEditing ? "Simpan Perubahan" : "Simpan Jenis Surat",
  );
  document.getElementById("admin-skip-template-btn").style.display = isEditing
    ? "block"
    : "none";
  // Menghapus hanya masuk akal untuk jenis surat yang sudah tersimpan.
  document.getElementById("admin-danger-zone").style.display = isEditing
    ? "block"
    : "none";
}

export function openAdminWizard() {
  resetAdminWizard();
  applyWizardMode(false);
  showView("view-admin-add");
}

export async function openEditWizard(slug) {
  resetAdminWizard();
  applyWizardMode(true);
  showView("view-admin-add");

  const statusEl = document.getElementById("admin-inspect-status");
  statusEl.className = "status show loading";
  statusEl.textContent = "Memuat konfigurasi…";

  try {
    const res = await fetch(`/admin/letter-types/${encodeURIComponent(slug)}`);
    if (!res.ok) throw new Error("Gagal memuat jenis surat.");
    const letterType = await res.json();

    editingSlug = letterType.slug;
    editingName = letterType.name;
    setText(document.getElementById("admin-delete-target"), letterType.name);
    document.getElementById("admin-name").value = letterType.name;
    document.getElementById("admin-slug").value = letterType.slug;
    // Slug yang sudah ada tidak boleh tertimpa otomatis saat nama disunting.
    slugManuallyEdited = true;

    renderAdminFieldsStep(
      (letterType.fields || []).map((f) => f.field_key),
      letterType.fields || [],
    );
    document.getElementById("admin-step-2").style.display = "block";
    statusEl.className = "status";
    statusEl.textContent = "";
  } catch (err) {
    statusEl.className = "status show error";
    statusEl.textContent = err.message;
  }
}

document
  .getElementById("admin-template-file")
  .addEventListener("change", (e) => {
    selectedTemplateFile = e.target.files[0] || null;
  });

document
  .getElementById("admin-inspect-btn")
  .addEventListener("click", async () => {
    const statusEl = document.getElementById("admin-inspect-status");
    if (!selectedTemplateFile) {
      statusEl.className = "status show error";
      statusEl.textContent =
        "Pilih file template docx terlebih dahulu.";
      return;
    }

    statusEl.className = "status show loading";
    statusEl.textContent = "Mendeteksi variabel…";

    try {
      const formData = new FormData();
      formData.append("template_file", selectedTemplateFile);
      const res = await fetch("/admin/letter-types/inspect", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal mendeteksi variabel.",
        );

      detectedVariables = data.detected_variables || [];
      statusEl.className = "status";
      statusEl.textContent = "";
      // Saat menyunting, pengaturan yang sudah diisi dipertahankan untuk
      // variabel yang masih ada di template baru; yang hilang ikut lenyap,
      // yang baru muncul dengan nilai bawaan.
      renderAdminFieldsStep(detectedVariables, bacaFieldsDariForm());
      document.getElementById("admin-step-2").style.display = "block";
    } catch (err) {
      statusEl.className = "status show error";
      statusEl.textContent = err.message;
    }
  });

document
  .getElementById("admin-skip-template-btn")
  .addEventListener("click", () => {
    // Template lama tetap dipakai; cukup buka kembali langkah konfigurasi.
    document.getElementById("admin-template-file").value = "";
    selectedTemplateFile = null;
    document.getElementById("admin-inspect-status").className = "status";
    document.getElementById("admin-inspect-status").textContent = "";
    document.getElementById("admin-step-2").style.display = "block";
  });

/**
 * Baca kembali konfigurasi field dari baris-baris yang sedang tampil.
 * Dipakai saat menyimpan, dan saat template diganti di tengah penyuntingan
 * supaya isian yang sudah dikerjakan tidak hilang begitu saja.
 */
function bacaFieldsDariForm() {
  return Array.from(
    document.querySelectorAll("#admin-fields-list .admin-field-row"),
  ).map((row) => ({
    field_key: row.dataset.fieldKey,
    label:
      row.querySelector(".admin-field-label-input").value.trim() ||
      row.dataset.fieldKey,
    field_type: row.querySelector(".admin-field-type-select").value,
    level: row.querySelector(".admin-field-level-select").value,
    required: row.querySelector(".admin-field-required-checkbox").checked,
  }));
}

document
  .getElementById("admin-delete-confirm")
  .addEventListener("input", (e) => {
    // Tombol baru aktif kalau nama diketik ulang persis. Perbandingannya
    // sengaja ketat (peka huruf besar-kecil) supaya penghapusan benar-benar
    // disengaja, bukan hasil salah klik.
    document.getElementById("admin-delete-btn").disabled =
      e.target.value.trim() !== editingName;
  });

document
  .getElementById("admin-delete-btn")
  .addEventListener("click", async () => {
    const statusEl = document.getElementById("admin-delete-status");
    const confirmValue = document
      .getElementById("admin-delete-confirm")
      .value.trim();

    if (!editingSlug || confirmValue !== editingName) return;

    statusEl.className = "status show loading";
    statusEl.textContent = "Memindahkan ke arsip…";
    document.getElementById("admin-delete-btn").disabled = true;

    try {
      const res = await fetch(
        `/admin/letter-types/${encodeURIComponent(editingSlug)}` +
          `?confirm_name=${encodeURIComponent(confirmValue)}`,
        { method: "DELETE" },
      );
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal menghapus jenis surat.",
        );

      statusEl.className = "status show success";
      statusEl.textContent = `Jenis surat "${editingName}" dipindahkan ke arsip. Bisa dipulihkan kapan saja dari halaman arsip.`;
      setTimeout(() => {
        showView("view-dashboard");
        loadDashboard();
      }, 1400);
    } catch (err) {
      statusEl.className = "status show error";
      statusEl.textContent = err.message;
      document.getElementById("admin-delete-btn").disabled = false;
    }
  });

function humanizeKey(key) {
  return key
    .split("_")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

/**
 * Bangun satu baris pengaturan untuk tiap variabel yang terdeteksi di template.
 *
 * `existingFields` diisi saat menyunting: konfigurasi yang sudah tersimpan
 * dipakai sebagai nilai awal, dicocokkan berdasarkan field_key. Variabel yang
 * belum punya konfigurasi (misal baru muncul setelah template diganti) jatuh ke
 * nilai bawaan seperti saat menambah jenis surat baru.
 */
function renderAdminFieldsStep(variables, existingFields = []) {
  const list = document.getElementById("admin-fields-list");
  list.innerHTML = "";
  document.getElementById("admin-no-vars-note").style.display =
    variables.length === 0 ? "block" : "none";

  const tersimpan = new Map(existingFields.map((f) => [f.field_key, f]));

  variables.forEach((key) => {
    const awal = tersimpan.get(key);
    const row = document.createElement("div");
    row.className = "admin-field-row";
    row.dataset.fieldKey = key;

    // Tiap kontrol diberi id sendiri supaya label bisa ditautkan dengannya.
    // Tanpa itu pembaca layar tidak tahu label mana milik kontrol yang mana.
    const labelId = `admin-label-${key}`;
    const typeId = `admin-type-${key}`;
    const levelId = `admin-level-${key}`;

    const keyCol = document.createElement("div");
    keyCol.className = "field";
    const keyLabel = document.createElement("label");
    keyLabel.className = "field-key-label";
    keyLabel.setAttribute("for", labelId);
    keyLabel.textContent = `{{ ${key} }}`;
    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.id = labelId;
    labelInput.className = "admin-field-label-input";
    labelInput.value = awal ? awal.label : humanizeKey(key);
    keyCol.append(keyLabel, labelInput);

    const typeCol = document.createElement("div");
    typeCol.className = "field";
    const typeLabel = setText(document.createElement("label"), "Tipe");
    typeLabel.setAttribute("for", typeId);
    const typeSelect = document.createElement("select");
    typeSelect.id = typeId;
    typeSelect.className = "admin-field-type-select";
    [
      ["text", "Teks"],
      ["date", "Tanggal"],
      ["number", "Angka"],
    ].forEach(([value, text]) => {
      const opt = new Option(text, value);
      typeSelect.appendChild(opt);
    });
    if (awal) typeSelect.value = awal.field_type;
    typeCol.append(typeLabel, typeSelect);

    const levelCol = document.createElement("div");
    levelCol.className = "field";
    const levelLabel = setText(
      document.createElement("label"),
      "Level",
    );
    levelLabel.setAttribute("for", levelId);
    const levelSelect = document.createElement("select");
    levelSelect.id = levelId;
    levelSelect.className = "admin-field-level-select";
    [
      ["batch", "Sekali per surat"],
      ["recipient", "Per penerima"],
    ].forEach(([value, text]) => {
      const opt = new Option(text, value);
      levelSelect.appendChild(opt);
    });
    if (awal) levelSelect.value = awal.level;
    levelCol.append(levelLabel, levelSelect);

    const requiredCol = document.createElement("label");
    requiredCol.className = "admin-required-toggle";
    const requiredCheckbox = document.createElement("input");
    requiredCheckbox.type = "checkbox";
    requiredCheckbox.id = `admin-required-${key}`;
    requiredCheckbox.className = "admin-field-required-checkbox";
    requiredCheckbox.checked = awal ? !!awal.required : true;
    requiredCol.append(
      requiredCheckbox,
      document.createTextNode("Wajib"),
    );
    // Tanggal di surat resmi selalu wajib — kunci checkbox-nya kalau
    // tipe field diubah jadi "date", dan lepas lagi kalau bukan.
    const syncRequiredLock = () => {
        const isDate = typeSelect.value === "date";
        if (isDate) requiredCheckbox.checked = true;
        requiredCheckbox.disabled = isDate;
        requiredCol.title = isDate ? "Field tanggal selalu wajib diisi." : "";
    };
    typeSelect.addEventListener("change", syncRequiredLock);
    syncRequiredLock();

    row.append(keyCol, typeCol, levelCol, requiredCol);
    list.appendChild(row);
  });
}

document.getElementById("admin-name").addEventListener("input", (e) => {
  if (!slugManuallyEdited) {
    document.getElementById("admin-slug").value = slugify(
      e.target.value,
    );
  }
});
document.getElementById("admin-slug").addEventListener("input", () => {
  slugManuallyEdited = true;
});

document
  .getElementById("admin-submit-btn")
  .addEventListener("click", async () => {
    const statusEl = document.getElementById("admin-submit-status");
    const name = document.getElementById("admin-name").value.trim();
    const slug = document.getElementById("admin-slug").value.trim();

    if (!name || !slug) {
      statusEl.className = "status show error";
      statusEl.textContent = "Nama dan slug jenis surat wajib diisi.";
      return;
    }
    // Saat menambah, template wajib ada. Saat menyunting, template lama tetap
    // dipakai kalau admin tidak mengunggah yang baru.
    const sedangMenyunting = editingSlug !== null;
    if (!sedangMenyunting && !selectedTemplateFile) {
      statusEl.className = "status show error";
      statusEl.textContent =
        "Template docx tidak ditemukan, silakan upload ulang di langkah 1.";
      return;
    }

    const fieldsConfig = bacaFieldsDariForm();

    statusEl.className = "status show loading";
    statusEl.textContent = sedangMenyunting
      ? "Menyimpan perubahan…"
      : "Menyimpan jenis surat…";

    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("fields_config", JSON.stringify(fieldsConfig));
      if (selectedTemplateFile) {
        formData.append("template_file", selectedTemplateFile);
      }

      let url = "/admin/letter-types";
      let method = "POST";
      if (sedangMenyunting) {
        url = `/admin/letter-types/${encodeURIComponent(editingSlug)}`;
        method = "PUT";
        formData.append("new_slug", slug);
      } else {
        formData.append("slug", slug);
      }

      const res = await fetch(url, { method, body: formData });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal menyimpan jenis surat.",
        );

      statusEl.className = "status show success";
      statusEl.textContent = sedangMenyunting
        ? `Perubahan pada "${data.name}" berhasil disimpan.`
        : `Jenis surat "${data.name}" berhasil dibuat.`;
      setTimeout(() => {
        showView("view-dashboard");
        loadDashboard();
      }, 900);
    } catch (err) {
      statusEl.className = "status show error";
      statusEl.textContent = err.message;
    }
  });