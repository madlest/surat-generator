// Titik masuk aplikasi: menyalakan tema, menyambungkan aksi antar tampilan,
// lalu memuat dashboard pertama kali.

import { initTheme } from "./theme.js";
import { showView } from "./views.js";
import { initDashboard, loadDashboard } from "./dashboard.js";
import { openForm } from "./form.js";
import { openAdminWizard, openEditWizard } from "./admin.js";
import { initArchive, loadArchive } from "./archive.js";

initTheme();

document.getElementById("footer-year").textContent = new Date().getFullYear();

// Dashboard tidak tahu apa-apa soal form maupun wizard; kaitannya dipasang
// di sini supaya modul-modul itu tidak perlu saling mengimpor.
initDashboard({
  onSelectType: openForm,
  onAddNew: openAdminWizard,
  onEditType: openEditWizard,
});

function backToDashboard() {
  showView("view-dashboard");
  loadDashboard();
}

// Jenis surat yang baru dipulihkan harus langsung tampak di dashboard.
initArchive({ onRestored: loadDashboard });

document.getElementById("open-archive-btn").addEventListener("click", () => {
  showView("view-archive");
  loadArchive();
});
document
  .getElementById("back-to-dashboard-from-archive")
  .addEventListener("click", backToDashboard);

document
  .getElementById("back-to-dashboard-from-form")
  .addEventListener("click", backToDashboard);
document
  .getElementById("back-to-dashboard-from-admin")
  .addEventListener("click", backToDashboard);

loadDashboard();