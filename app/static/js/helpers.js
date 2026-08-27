// Utilitas kecil yang dipakai lintas tampilan: penulisan teks yang aman,
// penanganan input tanggal, dan penomoran ulang langkah form.

export function setText(el, text) {
  el.textContent = text;
  return el;
}

export function formatDateIndonesia(value) {
  if (!value) return "";
  const [year, month, day] = value.split("-");
  return `${day}-${month}-${year}`;
}

export function parseDateIndonesia(value) {
  const match = value.trim().match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
  if (!match) return "";
  const [, day, month, year] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  if (
    date.getFullYear() !== Number(year) ||
    date.getMonth() !== Number(month) - 1 ||
    date.getDate() !== Number(day)
  ) {
    return "";
  }
  return `${year}-${month.padStart(2, "0")}-${day.padStart(2, "0")}`;
}

export function setupDateField(nativeId) {
  const dateInput = document.getElementById(nativeId);
  const displayInput = document.getElementById(`${nativeId}_display`);
  if (!dateInput || !displayInput) return;

  const syncDisplay = () => {
    displayInput.value = formatDateIndonesia(dateInput.value);
    dateInput.setCustomValidity("");
  };
  dateInput.addEventListener("change", syncDisplay);
  displayInput.addEventListener("input", () => {
    const isoDate = parseDateIndonesia(displayInput.value);
    dateInput.value = isoDate;
    dateInput.setCustomValidity(
      displayInput.value && !isoDate
        ? "Gunakan format DD-MM-YYYY dan masukkan tanggal yang valid."
        : "",
    );
    dateInput.dispatchEvent(new Event("input", { bubbles: true }));
  });

  const pickerButton = document.querySelector(
    `[data-date-target="${nativeId}"]`,
  );
  if (pickerButton) {
    pickerButton.addEventListener("click", () => {
      if (typeof dateInput.showPicker === "function") {
        dateInput.showPicker();
      } else {
        dateInput.focus();
        dateInput.click();
      }
    });
  }
}

export function dateFieldMarkup(nativeId, labelText, required) {
  return `
    <div class="field">
      <span class="field-label-text" data-label-for="${nativeId}"></span>
      <div class="date-input">
        <input type="text" class="date-display" id="${nativeId}_display" placeholder="Contoh: 22-08-2026"
          inputmode="numeric" autocomplete="off" aria-describedby="${nativeId}_hint">
        <input type="date" class="date-native" id="${nativeId}" lang="id-ID" ${required ? "required" : ""}
          aria-label="${labelText}">
        <button type="button" class="date-picker-btn" data-date-target="${nativeId}"
          title="Pilih tanggal dari kalender" aria-label="Pilih tanggal dari kalender">&#128197;</button>
      </div>
      <small class="field-hint" id="${nativeId}_hint">Format: DD-MM-YYYY</small>
    </div>
  `;
}

export function renumberSteps(container) {
  container.querySelectorAll(".step").forEach((step, index) => {
    const num = step.querySelector(".step-num");
    if (num) num.textContent = String(index + 1);
  });
}
