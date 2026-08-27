// Mode gelap/terang. Pilihan pengguna disimpan di localStorage; kalau belum
// pernah memilih, ikuti preferensi sistem.

export function initTheme() {
  const themeToggle = document.getElementById("theme-toggle");
  const themeIcon = document.getElementById("theme-icon");

  function applyTheme(isDark) {
    document.body.classList.toggle("dark", isDark);
    themeIcon.textContent = isDark ? "☀" : "☾";
    themeToggle.setAttribute("aria-pressed", String(isDark));
    themeToggle.setAttribute(
      "aria-label",
      isDark ? "Gunakan mode terang" : "Gunakan mode gelap",
    );
    themeToggle.title = isDark
      ? "Gunakan mode terang"
      : "Gunakan mode gelap";
    localStorage.setItem(
      "surat-generator-theme",
      isDark ? "dark" : "light",
    );
  }
  const savedTheme = localStorage.getItem("surat-generator-theme");
  const prefersDark = window.matchMedia?.(
    "(prefers-color-scheme: dark)",
  ).matches;
  applyTheme(savedTheme ? savedTheme === "dark" : prefersDark);
  themeToggle.addEventListener("click", () =>
    applyTheme(!document.body.classList.contains("dark")),
  );
}
