// Toolbar + pratinjau untuk <textarea> penulisan pesan. Dua "rasa":
//   flavor "md" — Markdown (badan email). Pratinjau via server.
//   flavor "wa" — format WhatsApp. Pratinjau client-side (waFormatToHtml).
//
// Tanpa dependensi. Toolbar cuma menyisipkan/membungkus teks — editor tetap
// <textarea> biasa, jadi mudah diprediksi & di-copy-paste.

function fireInput(ta) {
  ta.dispatchEvent(new Event("input", { bubbles: true }));
}

// Bungkus seleksi (atau titik kursor) dengan penanda inline.
function wrapSelection(ta, before, after = before) {
  const { selectionStart: s, selectionEnd: e, value: v } = ta;
  const sel = v.slice(s, e) || "teks";
  ta.value = v.slice(0, s) + before + sel + after + v.slice(e);
  ta.focus();
  ta.selectionStart = s + before.length;
  ta.selectionEnd = s + before.length + sel.length;
  fireInput(ta);
}

// Tambahkan prefix ke tiap baris yang tersentuh seleksi (list, kutipan, judul).
function prefixLines(ta, makePrefix) {
  const { selectionStart: s, selectionEnd: e, value: v } = ta;
  const lineStart = v.lastIndexOf("\n", s - 1) + 1;
  let lineEnd = v.indexOf("\n", e);
  if (lineEnd === -1) lineEnd = v.length;
  const newBlock = v
    .slice(lineStart, lineEnd)
    .split("\n")
    .map((ln, i) => makePrefix(i) + ln)
    .join("\n");
  ta.value = v.slice(0, lineStart) + newBlock + v.slice(lineEnd);
  ta.focus();
  ta.selectionStart = lineStart;
  ta.selectionEnd = lineStart + newBlock.length;
  fireInput(ta);
}

const BUTTONS = {
  md: [
    ["B", "Tebal", (ta) => wrapSelection(ta, "**")],
    ["I", "Miring", (ta) => wrapSelection(ta, "_")],
    ["H", "Judul", (ta) => prefixLines(ta, () => "## ")],
    ["• List", "Daftar berpoin", (ta) => prefixLines(ta, () => "- ")],
    ["1. List", "Daftar bernomor", (ta) => prefixLines(ta, (i) => `${i + 1}. `)],
    ["“ ”", "Kutipan", (ta) => prefixLines(ta, () => "> ")],
    ["🔗", "Tautan", (ta) => wrapSelection(ta, "[", "](https://)")],
  ],
  wa: [
    ["B", "Tebal", (ta) => wrapSelection(ta, "*")],
    ["I", "Miring", (ta) => wrapSelection(ta, "_")],
    ["S", "Coret", (ta) => wrapSelection(ta, "~")],
    ["</>", "Monospace", (ta) => wrapSelection(ta, "```")],
    ["• List", "Daftar berpoin", (ta) => prefixLines(ta, () => "- ")],
    ["1. List", "Daftar bernomor", (ta) => prefixLines(ta, (i) => `${i + 1}. `)],
    ["“ ”", "Kutipan", (ta) => prefixLines(ta, () => "> ")],
  ],
};

// --- Pratinjau WhatsApp (client-side) ----------------------------------

function esc(s) {
  return s.replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

function waInline(s) {
  // Escape dulu, lalu ganti penanda WhatsApp. Penanda menempel ke kata (boleh
  // diikuti tanda baca), tidak boleh ada penanda lain di dalamnya. Pendekatan,
  // bukan replika persis WhatsApp.
  const mark = (ch) =>
    new RegExp(`(^|[^\\w${ch}])\\${ch}([^${ch}\\s](?:[^${ch}\\n]*[^${ch}\\s])?)\\${ch}(?![\\w${ch}])`, "g");
  return esc(s)
    .replace(/```([^`]+)```/g, "<code>$1</code>")
    .replace(mark("*"), "$1<b>$2</b>")
    .replace(mark("_"), "$1<i>$2</i>")
    .replace(mark("~"), "$1<s>$2</s>");
}

export function waFormatToHtml(text) {
  const lines = (text || "").split("\n");
  const out = [];
  let list = null; // "ul" | "ol" | null

  const closeList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };

  for (const raw of lines) {
    const bullet = raw.match(/^[-*]\s+(.*)$/);
    const numbered = raw.match(/^\d+\.\s+(.*)$/);
    const quote = raw.match(/^>\s?(.*)$/);

    if (bullet) {
      if (list !== "ul") {
        closeList();
        out.push("<ul>");
        list = "ul";
      }
      out.push(`<li>${waInline(bullet[1])}</li>`);
    } else if (numbered) {
      if (list !== "ol") {
        closeList();
        out.push("<ol>");
        list = "ol";
      }
      out.push(`<li>${waInline(numbered[1])}</li>`);
    } else if (quote) {
      closeList();
      out.push(`<blockquote>${waInline(quote[1])}</blockquote>`);
    } else if (raw.trim() === "") {
      closeList();
      out.push("<br>");
    } else {
      closeList();
      out.push(`${waInline(raw)}<br>`);
    }
  }
  closeList();
  return out.join("\n");
}

// --- Rakit toolbar + panel pratinjau -----------------------------------

/**
 * @param {HTMLTextAreaElement} textarea
 * @param {"md"|"wa"} flavor
 * @param {(md: string) => Promise<string>} renderPreview  async -> HTML string
 */
export function attachComposer(textarea, flavor, renderPreview) {
  if (!textarea || textarea.dataset.composerReady) return;
  textarea.dataset.composerReady = "1";

  const bar = document.createElement("div");
  bar.className = "composer-toolbar";
  BUTTONS[flavor].forEach(([label, title, fn]) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "composer-btn";
    b.textContent = label;
    b.title = title;
    b.addEventListener("click", () => fn(textarea));
    bar.appendChild(b);
  });

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "composer-btn composer-preview-toggle";
  toggle.textContent = "Pratinjau";
  bar.appendChild(toggle);

  const preview = document.createElement("div");
  preview.className = "composer-preview";
  preview.hidden = true;

  textarea.before(bar);
  textarea.after(preview);

  let shown = false;
  let timer = null;

  const refresh = async () => {
    if (!shown) return;
    try {
      preview.innerHTML = await renderPreview(textarea.value);
    } catch {
      preview.textContent = "(pratinjau gagal dimuat)";
    }
  };

  toggle.addEventListener("click", () => {
    shown = !shown;
    preview.hidden = !shown;
    toggle.classList.toggle("active", shown);
    refresh();
  });

  textarea.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(refresh, 350);
  });
}
