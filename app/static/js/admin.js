// Wizard admin: tambah jenis surat baru dalam dua langkah — unggah template
// untuk mendeteksi variabelnya, lalu atur label, tipe, dan level tiap field.

import { setText } from "./helpers.js";
import { showView } from "./views.js";
import { loadDashboard } from "./dashboard.js";

let selectedTemplateFile = null;
let detectedVariables = [];
let slugManuallyEdited = false;

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

export function openAdminWizard() {
  resetAdminWizard();
  showView("view-admin-add");
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
      renderAdminFieldsStep(detectedVariables);
      document.getElementById("admin-step-2").style.display = "block";
    } catch (err) {
      statusEl.className = "status show error";
      statusEl.textContent = err.message;
    }
  });

function humanizeKey(key) {
  return key
    .split("_")
    .map((w) => (w ? w.charAt(0).toUpperCase() + w.slice(1) : w))
    .join(" ");
}

function renderAdminFieldsStep(variables) {
  const list = document.getElementById("admin-fields-list");
  list.innerHTML = "";
  document.getElementById("admin-no-vars-note").style.display =
    variables.length === 0 ? "block" : "none";

  variables.forEach((key) => {
    const row = document.createElement("div");
    row.className = "admin-field-row";
    row.dataset.fieldKey = key;

    const keyCol = document.createElement("div");
    keyCol.className = "field";
    const keyLabel = document.createElement("span");
    keyLabel.className = "field-key-label";
    keyLabel.textContent = `{{ ${key} }}`;
    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.className = "admin-field-label-input";
    labelInput.value = humanizeKey(key);
    keyCol.append(keyLabel, labelInput);

    const typeCol = document.createElement("div");
    typeCol.className = "field";
    const typeLabel = setText(document.createElement("label"), "Tipe");
    const typeSelect = document.createElement("select");
    typeSelect.className = "admin-field-type-select";
    [
      ["text", "Teks"],
      ["date", "Tanggal"],
      ["number", "Angka"],
    ].forEach(([value, text]) => {
      const opt = new Option(text, value);
      typeSelect.appendChild(opt);
    });
    typeCol.append(typeLabel, typeSelect);

    const levelCol = document.createElement("div");
    levelCol.className = "field";
    const levelLabel = setText(
      document.createElement("label"),
      "Level",
    );
    const levelSelect = document.createElement("select");
    levelSelect.className = "admin-field-level-select";
    [
      ["batch", "Sekali per surat"],
      ["recipient", "Per penerima"],
    ].forEach(([value, text]) => {
      const opt = new Option(text, value);
      levelSelect.appendChild(opt);
    });
    levelCol.append(levelLabel, levelSelect);

    const requiredCol = document.createElement("label");
    requiredCol.className = "admin-required-toggle";
    const requiredCheckbox = document.createElement("input");
    requiredCheckbox.type = "checkbox";
    requiredCheckbox.className = "admin-field-required-checkbox";
    requiredCheckbox.checked = true;
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
    if (!selectedTemplateFile) {
      statusEl.className = "status show error";
      statusEl.textContent =
        "Template docx tidak ditemukan, silakan upload ulang di langkah 1.";
      return;
    }

    const fieldsConfig = [];
    document
      .querySelectorAll("#admin-fields-list .admin-field-row")
      .forEach((row) => {
        fieldsConfig.push({
          field_key: row.dataset.fieldKey,
          label:
            row
              .querySelector(".admin-field-label-input")
              .value.trim() || row.dataset.fieldKey,
          field_type: row.querySelector(".admin-field-type-select")
            .value,
          level: row.querySelector(".admin-field-level-select").value,
          required: row.querySelector(".admin-field-required-checkbox")
            .checked,
        });
      });

    statusEl.className = "status show loading";
    statusEl.textContent = "Menyimpan jenis surat…";

    try {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("slug", slug);
      formData.append("fields_config", JSON.stringify(fieldsConfig));
      formData.append("template_file", selectedTemplateFile);

      const res = await fetch("/admin/letter-types", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      if (!res.ok)
        throw new Error(
          typeof data.detail === "string"
            ? data.detail
            : "Gagal menyimpan jenis surat.",
        );

      statusEl.className = "status show success";
      statusEl.textContent = `Jenis surat "${data.name}" berhasil dibuat.`;
      setTimeout(() => {
        showView("view-dashboard");
        loadDashboard();
      }, 900);
    } catch (err) {
      statusEl.className = "status show error";
      statusEl.textContent = err.message;
    }
  });
