// Form dinamis: merender isian surat berdasarkan definisi LetterField yang
// datang dari server, lalu mengirim job generate dan memantau progresnya.

import {
  dateFieldMarkup,
  renumberSteps,
  setText,
  setupDateField,
} from "./helpers.js";
import { showView } from "./views.js";

const formArea = document.getElementById("form-area");
const formTypeTag = document.getElementById("form-type-tag");
let currentLetterType = null;
// Mode pengisian penerima: "list" (isi baris satu per satu) atau "csv".
// Disimpan di level modul karena diubah oleh setupRecipientSection dan dibaca
// oleh setupSubmitHandler.
let recipientsMode = "list";

export async function openForm(slug) {
  showView("view-form");
  formTypeTag.textContent = "";
  formArea.innerHTML = "<p>Memuat form&hellip;</p>";
  try {
    const res = await fetch(
      `/admin/letter-types/${encodeURIComponent(slug)}`,
    );
    if (!res.ok) throw new Error("Gagal memuat jenis surat.");
    currentLetterType = await res.json();
    formTypeTag.textContent = `Jenis surat: ${currentLetterType.name}`;
    renderDynamicForm(currentLetterType);
  } catch (err) {
    formArea.innerHTML = "";
    const p = setText(document.createElement("p"), err.message);
    p.className = "dashboard-error";
    formArea.appendChild(p);
  }
}

function batchFieldMarkup(field) {
  const id = `field_${field.field_key}`;
  if (field.field_type === "date") {
    return dateFieldMarkup(id, field.label, field.required);
  }
  const inputType = field.field_type === "number" ? "number" : "text";
  return `
    <div class="field">
      <span class="field-label-text" data-label-for="${id}"></span>
      <input type="${inputType}" id="${id}" ${field.required ? "required" : ""}>
    </div>
  `;
}

function renderDynamicForm(letterType) {
  const fields = letterType.fields || [];
  const batchFields = fields.filter((f) => f.level === "batch");
  const recipientFields = fields.filter((f) => f.level === "recipient");

  formArea.innerHTML = `
    <form id="surat-form">
      <section class="step">
        <div class="step-head"><span class="step-num"></span><h2>Informasi Surat</h2></div>
        <div class="field-grid">
          <div class="field">
            <label for="nomor_surat">Nomor Surat</label>
            <input type="text" id="nomor_surat" required placeholder="Isikan nomor surat">
          </div>
          <div class="field">
            <label for="tempat_surat">Tempat Surat</label>
            <input type="text" id="tempat_surat" required placeholder="Isikan tempat surat">
          </div>
          ${dateFieldMarkup("tanggal_surat", "Tanggal Surat", true)}
          <div class="field">
            <label for="perihal_surat">Perihal</label>
            <input type="text" id="perihal_surat" required placeholder="Isikan perihal surat">
          </div>
        </div>
      </section>

      ${
        batchFields.length > 0
          ? `
      <section class="step">
        <div class="step-head">
          <span class="step-num"></span><h2>Detail Tambahan</h2>
          <span class="hint">Khusus jenis surat ini</span>
        </div>
        <div class="field-grid">
          ${batchFields.map(batchFieldMarkup).join("")}
        </div>
      </section>`
          : ""
      }

      <section class="step">
        <div class="step-head">
          <span class="step-num"></span><h2>Lampiran</h2>
          <span class="hint">Berlaku untuk semua penerima</span>
        </div>
        <div class="row-list" id="lampiran-list"></div>
        <button type="button" class="add-btn" id="add-lampiran">+ Tambahkan lampiran</button>
      </section>

      <section class="step">
        <div class="step-head"><span class="step-num"></span><h2>Penerima</h2></div>
        <div class="mode-toggle">
          <button type="button" class="mode-btn active" data-mode="list">Isi Daftar Langsung</button>
          <button type="button" class="mode-btn" data-mode="csv">Upload CSV</button>
        </div>
        <div id="mode-list">
          <div class="row-list" id="recipient-list"></div>
          <button type="button" class="add-btn" id="add-recipient">+ Tambahkan penerima</button>
        </div>
        <div id="mode-csv" style="display: none">
          <div class="field">
            <label for="recipients_csv">File CSV</label>
            <input type="file" id="recipients_csv" accept=".csv">
          </div>
          <p class="csv-hint">
            Kolom wajib: <code id="csv-columns-hint"></code>.
            <a href="#" id="download-template">Unduh contoh template CSV</a>
          </p>
        </div>
      </section>

      <section class="step">
        <div class="step-head"><span class="step-num"></span><h2>Buat Dokumen</h2></div>
        <div class="submit-area">
          <div class="stamp" id="stamp">SIAP<br>DIKIRIM</div>
          <button type="button" class="preview-btn" id="preview-btn" disabled>Preview Penerima Pertama</button>
          <button type="submit" class="submit" id="submit-btn">Generate &amp; Unduh ZIP</button>
        </div>
        <div class="status" id="status" role="status" aria-live="polite"></div>
        <div class="progress-wrap" id="progress-wrap">
          <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
          <div class="progress-label" id="progress-label"></div>
        </div>
      </section>
    </form>
  `;

  // fill in label texts safely (avoids HTML-escaping admin-typed labels)
  formArea
    .querySelectorAll(".field-label-text[data-label-for]")
    .forEach((span) => {
      const id = span.getAttribute("data-label-for");
      const field = batchFields.find(
        (f) => `field_${f.field_key}` === id,
      );
      const label = document.createElement("label");
      label.setAttribute("for", id);
      label.textContent =
        id === "tanggal_surat"
          ? "Tanggal Surat"
          : field
            ? field.label
            : "";
      span.replaceWith(label);
    });

  setupDateField("tanggal_surat");
  batchFields
    .filter((f) => f.field_type === "date")
    .forEach((f) => setupDateField(`field_${f.field_key}`));

  setupLampiranSection();
  setupRecipientSection(recipientFields);
  setupSubmitHandler(batchFields, recipientFields);

  renumberSteps(formArea);
  updateStampState();
}

function setupLampiranSection() {
  const lampiranList = document.getElementById("lampiran-list");
  let lampiranRowCount = 0;
  let draggedLampiranRow = null;

  function updateLampiranNumbers() {
    lampiranList
      .querySelectorAll(".lampiran-row")
      .forEach((row, index) => {
        const order = row.querySelector(".lampiran-order");
        order.textContent = index + 1;
        order.setAttribute(
          "aria-label",
          `Urutan lampiran ${index + 1}`,
        );
      });
  }

  lampiranList.addEventListener("dragover", (event) => {
    if (!draggedLampiranRow) return;
    event.preventDefault();
    const targetRow = event.target.closest(".lampiran-row");
    if (!targetRow || targetRow === draggedLampiranRow) return;
    const targetMiddle =
      targetRow.getBoundingClientRect().top +
      targetRow.getBoundingClientRect().height / 2;
    lampiranList.insertBefore(
      draggedLampiranRow,
      event.clientY < targetMiddle ? targetRow : targetRow.nextSibling,
    );
    updateLampiranNumbers();
  });

  function setupLampiranDrag(row) {
    const dragHandle = row.querySelector(".drag-handle");
    dragHandle.addEventListener("dragstart", (event) => {
      draggedLampiranRow = row;
      row.classList.add("dragging");
      row.setAttribute("aria-grabbed", "true");
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", row.dataset.lampiranId);
    });
    dragHandle.addEventListener("dragend", () => {
      row.classList.remove("dragging");
      row.setAttribute("aria-grabbed", "false");
      draggedLampiranRow = null;
      updateStampState();
    });
  }

  function addLampiranRow() {
    lampiranRowCount += 1;
    const rowId = lampiranRowCount;
    const row = document.createElement("div");
    row.className = "lampiran-row";
    row.dataset.lampiranId = rowId;
    row.setAttribute("aria-grabbed", "false");
    row.innerHTML = `
      <span class="lampiran-order" aria-label="Urutan lampiran">${rowId}</span>
      <button type="button" class="drag-handle" draggable="true" title="Seret untuk mengubah urutan" aria-label="Seret untuk mengubah urutan">&#9776;</button>
      <div class="field">
        <label for="lampiran-judul-${rowId}">Judul Lampiran</label>
        <input type="text" id="lampiran-judul-${rowId}" class="lampiran-judul" placeholder="Isikan judul lampiran" maxlength="150" required>
      </div>
      <div class="field">
        <label for="lampiran-file-${rowId}">File PDF</label>
        <input type="file" id="lampiran-file-${rowId}" class="lampiran-file" accept=".pdf,application/pdf" required>
      </div>
      <button type="button" class="remove-btn" title="Hapus lampiran ini" aria-label="Hapus lampiran ini">&#128465;</button>
    `;
    row.querySelector(".remove-btn").addEventListener("click", () => {
      row.remove();
      updateLampiranNumbers();
      updateStampState();
    });
    setupLampiranDrag(row);
    lampiranList.appendChild(row);
    updateLampiranNumbers();
    updateStampState();
  }

  document
    .getElementById("add-lampiran")
    .addEventListener("click", addLampiranRow);
  addLampiranRow();
}

function setupRecipientSection(recipientFields) {
  const recipientList = document.getElementById("recipient-list");
  const gridColumns = `auto ${"minmax(0, 1fr) ".repeat(recipientFields.length)}auto`;
  let recipientRowCount = 0;

  function updateRecipientNumbers() {
    recipientList
      .querySelectorAll(".recipient-row")
      .forEach((row, index) => {
        const order = row.querySelector(".recipient-order");
        order.textContent = index + 1;
        order.setAttribute(
          "aria-label",
          `Urutan penerima ${index + 1}`,
        );
      });
  }

  function addRecipientRow() {
    recipientRowCount += 1;
    const rowId = recipientRowCount;
    const row = document.createElement("div");
    row.className = "recipient-row";
    row.style.gridTemplateColumns = gridColumns;

    const order = document.createElement("span");
    order.className = "recipient-order";
    order.setAttribute("aria-label", "Urutan penerima");
    order.textContent = rowId;
    row.appendChild(order);

    recipientFields.forEach((field) => {
      const inputId = `rec-${field.field_key}-${rowId}`;

      if (field.field_type === "date") {
        const temp = document.createElement("div");
        temp.innerHTML = dateFieldMarkup(
          inputId,
          field.label,
          field.required,
        );
        const fieldDiv = temp.firstElementChild;
        const lbl = document.createElement("label");
        lbl.setAttribute("for", inputId);
        lbl.textContent = field.label;
        fieldDiv.querySelector(".field-label-text").replaceWith(lbl);
        const nativeInput = fieldDiv.querySelector("input.date-native");
        nativeInput.dataset.fieldKey = field.field_key;
        nativeInput.dataset.required = String(!!field.required);
        row.appendChild(fieldDiv);
        setupDateField(inputId);
      } else {
        const wrapper = document.createElement("div");
        wrapper.className = "field";
        const label = document.createElement("label");
        label.setAttribute("for", inputId);
        label.textContent = field.label;
        const input = document.createElement("input");
        input.type = field.field_type === "number" ? "number" : "text";
        input.id = inputId;
        input.dataset.fieldKey = field.field_key;
        input.dataset.required = String(!!field.required);
        input.required = !!field.required;
        input.placeholder = `Isikan ${field.label.toLowerCase()}`;
        wrapper.append(label, input);
        row.appendChild(wrapper);
      }
    });

    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "remove-btn";
    removeBtn.title = "Hapus penerima ini";
    removeBtn.setAttribute("aria-label", "Hapus penerima ini");
    removeBtn.innerHTML = "&#128465;";
    removeBtn.addEventListener("click", () => {
      row.remove();
      updateRecipientNumbers();
      updateStampState();
    });
    row.appendChild(removeBtn);

    recipientList.appendChild(row);
    updateRecipientNumbers();
    updateStampState();
  }

  document
    .getElementById("add-recipient")
    .addEventListener("click", addRecipientRow);
  addRecipientRow();

  // mode toggle (list vs csv)
  // Form dibangun ulang tiap kali jenis surat dibuka, jadi mode dikembalikan
  // ke default agar tidak terbawa dari jenis surat sebelumnya.
  recipientsMode = "list";
  const modeButtons = document.querySelectorAll(".mode-btn");
  const modeList = document.getElementById("mode-list");
  const modeCsv = document.getElementById("mode-csv");
  const csvColumnsHint = document.getElementById("csv-columns-hint");
  csvColumnsHint.textContent = recipientFields
    .map((f) => f.field_key)
    .join(", ");
  if (recipientFields.some((f) => f.field_type === "date")) {
    const dateNote = document.createElement("small");
    dateNote.className = "field-hint";
    dateNote.style.display = "block";
    dateNote.style.marginTop = "4px";
    dateNote.textContent =
      "Untuk kolom bertipe tanggal, isi dengan format DD-MM-YYYY (mis. 22-08-2026).";
    modeCsv.querySelector(".csv-hint").after(dateNote);
  }

  modeButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      modeButtons.forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      recipientsMode = btn.dataset.mode;
      modeList.style.display =
        recipientsMode === "list" ? "block" : "none";
      modeCsv.style.display =
        recipientsMode === "csv" ? "block" : "none";

      const isListMode = recipientsMode === "list";
      recipientList
        .querySelectorAll("[data-field-key]")
        .forEach((el) => {
          el.required = isListMode && el.dataset.required === "true";
        });
      document.getElementById("recipients_csv").required = !isListMode;

      updateStampState();
    });
  });
  document
    .getElementById("recipients_csv")
    .addEventListener("change", updateStampState);
  document
    .getElementById("download-template")
    .addEventListener("click", (e) => {
      e.preventDefault();
      const header = recipientFields.map((f) => f.field_key).join(",");
      const blob = new Blob([`${header}\n`], {
        type: "text/csv;charset=utf-8;",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "template_recipients.csv";
      a.click();
      URL.revokeObjectURL(url);
    });
}

/**
 * Kumpulkan seluruh isian form (info surat, lampiran, penerima) jadi satu
 * FormData siap kirim ke endpoint generate maupun preview — keduanya
 * menerima payload yang sama persis.
 *
 * Mengembalikan { formData } kalau berhasil, atau { error } kalau ada isian
 * yang tidak valid (mis. lampiran bukan PDF, CSV belum dipilih). Pemanggil
 * cukup cek salah satu field yang ada.
 */
function collectFormData(batchFields, recipientFields) {
  const lampiranJudulEls = document.querySelectorAll(".lampiran-judul");
  const lampiranFileEls = document.querySelectorAll(".lampiran-file");
  const lampirans = [];
  const lampiranFiles = [];
  lampiranJudulEls.forEach((el, i) => {
    lampirans.push({ judul: el.value });
    lampiranFiles.push(lampiranFileEls[i].files[0]);
  });

  const invalidLampiran = lampiranFiles.find(
    (file) =>
      !file ||
      (!file.type.includes("pdf") &&
        !file.name.toLowerCase().endsWith(".pdf")) ||
      file.size > 10 * 1024 * 1024,
  );
  if (invalidLampiran) {
    return {
      error: "Setiap lampiran harus berupa PDF dengan ukuran maksimal 10 MB.",
    };
  }

  const customFields = {};
  batchFields.forEach((f) => {
    const el = document.getElementById(`field_${f.field_key}`);
    customFields[f.field_key] = el ? el.value : "";
  });

  const batchInfo = {
    nomor_surat: document.getElementById("nomor_surat").value,
    tempat_surat: document.getElementById("tempat_surat").value,
    tanggal_surat: document.getElementById("tanggal_surat").value,
    perihal_surat: document.getElementById("perihal_surat").value,
    lampirans: lampirans,
    custom_fields: customFields,
  };

  const formData = new FormData();
  formData.append("batch_info", JSON.stringify(batchInfo));
  lampiranFiles.forEach((file) => formData.append("lampiran_files", file));

  formData.append("recipients_mode", recipientsMode);

  if (recipientsMode === "list") {
    const recipients = [];
    document
      .querySelectorAll("#recipient-list .recipient-row")
      .forEach((row) => {
        const rec = {};
        recipientFields.forEach((f) => {
          const el = row.querySelector(`[data-field-key="${f.field_key}"]`);
          rec[f.field_key] = el ? el.value : "";
        });
        recipients.push(rec);
      });
    formData.append("recipients_json", JSON.stringify(recipients));
  } else {
    const csvFile = document.getElementById("recipients_csv").files[0];
    if (!csvFile) {
      return { error: "Pilih file CSV terlebih dahulu." };
    }
    formData.append("recipients_csv", csvFile);
  }

  return { formData };
}

function updateStampState() {
  const form = document.getElementById("surat-form");
  const stampEl = document.getElementById("stamp");
  const previewBtn = document.getElementById("preview-btn");
  if (!form || !stampEl) return;
  const isValid = form.checkValidity();
  stampEl.classList.toggle("ready", isValid);
  if (previewBtn) previewBtn.disabled = !isValid;
}

function setupSubmitHandler(batchFields, recipientFields) {
  const form = document.getElementById("surat-form");
  form.addEventListener("input", updateStampState);

  const statusEl = document.getElementById("status");
  const submitBtn = document.getElementById("submit-btn");
  const progressWrap = document.getElementById("progress-wrap");
  const progressFill = document.getElementById("progress-fill");
  const progressLabel = document.getElementById("progress-label");

  function setStatus(type, message) {
    statusEl.className = "status show " + type;
    statusEl.textContent = message;
  }
  function clearStatus() {
    statusEl.className = "status";
    statusEl.textContent = "";
  }
  function errorDetailToMessage(detail) {
    if (Array.isArray(detail)) return detail.join("; ");
    if (typeof detail === "string") return detail;
    return JSON.stringify(detail);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearStatus();
    progressWrap.classList.remove("show");
    progressFill.style.width = "0%";
    progressLabel.textContent = "";

    const { formData, error } = collectFormData(batchFields, recipientFields);
    if (error) {
      setStatus("error", error);
      return;
    }

    submitBtn.disabled = true;
    setStatus("loading", "Mengirim data ke server…");

    try {
      const response = await fetch(
        `/generate/${encodeURIComponent(currentLetterType.unit_slug)}/${encodeURIComponent(currentLetterType.slug)}`,
        {
          method: "POST",
          body: formData,
        },
      );

      if (!response.ok) {
        let detail = "Terjadi kesalahan saat memproses dokumen.";
        try {
          const errJson = await response.json();
          detail = errorDetailToMessage(errJson.detail);
        } catch (_) {
          /* biarkan pesan default */
        }
        setStatus("error", detail);
        submitBtn.disabled = false;
        return;
      }

      const { job_id, total } = await response.json();
      progressWrap.classList.add("show");
      setStatus("loading", "Memproses dokumen…");
      progressLabel.textContent = `0/${total} dokumen selesai`;

      const pollInterval = setInterval(async () => {
        try {
          const statusRes = await fetch(
            `/generate/jobs/${job_id}/status`,
          );
          if (!statusRes.ok) {
            clearInterval(pollInterval);
            setStatus("error", "Gagal memeriksa status proses.");
            submitBtn.disabled = false;
            return;
          }
          const jobStatus = await statusRes.json();
          const pct =
            jobStatus.total > 0
              ? Math.round((jobStatus.current / jobStatus.total) * 100)
              : 0;
          progressFill.style.width = pct + "%";
          progressLabel.textContent = `${jobStatus.current}/${jobStatus.total} dokumen selesai`;

          if (jobStatus.status === "done") {
            clearInterval(pollInterval);
            setStatus("loading", "Menyiapkan unduhan…");

            const downloadRes = await fetch(
              `/generate/jobs/${job_id}/download`,
            );
            if (!downloadRes.ok) {
              setStatus("error", "Gagal mengunduh hasil.");
              submitBtn.disabled = false;
              return;
            }
            const blob = await downloadRes.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `hasil_${currentLetterType.slug}.zip`;
            a.click();
            URL.revokeObjectURL(url);

            setStatus(
              "success",
              "Dokumen berhasil dibuat dan diunduh.",
            );
            submitBtn.disabled = false;
          } else if (jobStatus.status === "error") {
            clearInterval(pollInterval);
            setStatus(
              "error",
              jobStatus.error ||
                "Terjadi kesalahan saat memproses dokumen.",
            );
            submitBtn.disabled = false;
          }
        } catch (err) {
          clearInterval(pollInterval);
          setStatus(
            "error",
            "Tidak dapat terhubung ke server: " + err.message,
          );
          submitBtn.disabled = false;
        }
      }, 1200);
    } catch (err) {
      setStatus(
        "error",
        "Tidak dapat terhubung ke server: " + err.message,
      );
      submitBtn.disabled = false;
    }
  });

  const previewBtn = document.getElementById("preview-btn");
  previewBtn.addEventListener("click", async () => {
    // Tombol sudah di-disable lewat updateStampState kalau form belum valid,
    // tapi dicek lagi di sini untuk jaga-jaga (mis. browser lama yang tidak
    // menghormati atribut disabled secara konsisten).
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }

    const { formData, error } = collectFormData(batchFields, recipientFields);
    if (error) {
      setStatus("error", error);
      return;
    }

    previewBtn.disabled = true;
    submitBtn.disabled = true;
    clearStatus();
    setStatus("loading", "Menyiapkan pratinjau…");

    try {
      const response = await fetch(
        `/generate/${encodeURIComponent(currentLetterType.unit_slug)}/${encodeURIComponent(currentLetterType.slug)}/preview`,
        {
          method: "POST",
          body: formData,
        },
      );

      if (!response.ok) {
        let detail = "Gagal membuat pratinjau.";
        try {
          const errJson = await response.json();
          detail = errorDetailToMessage(errJson.detail);
        } catch (_) {
          /* biarkan pesan default */
        }
        setStatus("error", detail);
        return;
      }

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
      // Ditunda, bukan langsung, supaya tab baru sempat memuat PDF-nya
      // sebelum object URL-nya dicabut.
      setTimeout(() => URL.revokeObjectURL(url), 60_000);

      clearStatus();
    } catch (err) {
      setStatus(
        "error",
        "Tidak dapat terhubung ke server: " + err.message,
      );
    } finally {
      previewBtn.disabled = !form.checkValidity();
      submitBtn.disabled = false;
    }
  });
}