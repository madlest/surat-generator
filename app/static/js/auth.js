// Gerbang autentikasi. Dijalankan paling awal oleh app.js: memanggil
// /auth/me, lalu memutuskan apakah aplikasi ditampilkan (onAuthed) atau
// pengguna diarahkan ke layar masuk (onAnonymous).
//
// Logout memakai <form method="post" action="/auth/logout"> di index.html —
// tidak perlu JS di sini, biar tetap jalan walau modul ini gagal dimuat.

let currentUser = null;

export function getCurrentUser() {
  return currentUser;
}

const topbar = document.getElementById("topbar");
const topbarName = document.getElementById("topbar-name");
const topbarMeta = document.getElementById("topbar-meta");
const topbarSuperadminBtn = document.getElementById("topbar-superadmin-btn");
const loginStatus = document.getElementById("login-status");

const topbarGmail = document.getElementById("topbar-gmail");
const gmailDot = document.getElementById("gmail-dot");
const gmailLabel = document.getElementById("gmail-label");
const gmailConnectBtn = document.getElementById("gmail-connect-btn");
const gmailDisconnectBtn = document.getElementById("gmail-disconnect-btn");
const appBanner = document.getElementById("app-banner");
const appBannerText = document.getElementById("app-banner-text");

const ROLE_LABEL = {
  superadmin: "Superadmin",
  admin: "Admin",
};

// Pesan untuk ?auth_error=<code> yang dikirim /auth/callback saat login gagal
// (lihat _auth_error_redirect di app/routers/auth.py).
const AUTH_ERROR_MESSAGE = {
  not_invited:
    "Akun Google ini belum diundang. Minta superadmin unit Anda mendaftarkan email Anda dulu, lalu coba masuk lagi.",
  deactivated:
    "Akses akun Anda sudah dinonaktifkan. Hubungi superadmin unit Anda kalau ini keliru.",
  oauth:
    "Gagal memverifikasi akun Google. Pastikan Anda memakai akun @umbjm.ac.id yang benar dan sudah terverifikasi.",
  expired: "Sesi masuk kedaluwarsa atau tidak valid. Silakan coba masuk lagi.",
  cancelled: "Proses masuk dibatalkan.",
};

// Diambil sekali saat modul dimuat, sebelum URL dibersihkan, supaya pesannya
// tetap tampil walaupun /auth/me kebetulan lambat.
function takeAuthErrorFromUrl() {
  let code = null;
  try {
    code = new URLSearchParams(window.location.search).get("auth_error");
  } catch {
    return null;
  }
  if (!code) return null;
  // Buang query-nya supaya refresh tidak memunculkan pesan yang sama lagi.
  try {
    window.history.replaceState(null, "", window.location.pathname);
  } catch {
    /* replaceState bisa gagal di konteks tertentu — pesan tetap tampil. */
  }
  return AUTH_ERROR_MESSAGE[code] || "Tidak bisa menyelesaikan proses masuk. Silakan coba lagi.";
}

const pendingAuthError = takeAuthErrorFromUrl();

// Hasil alur "Hubungkan Gmail" (?gmail=connected atau ?gmail_error=<kode>),
// dikirim /auth/gmail/callback. Lihat _gmail_result_redirect di auth.py.
const GMAIL_RESULT_MESSAGE = {
  connected: { type: "success", text: "Gmail berhasil dihubungkan. Sekarang Anda bisa mengirim surat via email." },
  cancelled: { type: "info", text: "Proses menghubungkan Gmail dibatalkan." },
  expired: { type: "error", text: "Sesi menghubungkan Gmail kedaluwarsa. Coba lagi." },
  oauth: { type: "error", text: "Gagal memverifikasi akun Google. Pastikan memakai akun @umbjm.ac.id Anda." },
  wrong_account: {
    type: "error",
    text: "Akun Google yang Anda pilih berbeda dari akun yang login di aplikasi ini. Pilih akun yang sama.",
  },
  scope_declined: {
    type: "error",
    text: "Izin mengirim email tidak dicentang. Ulangi dan izinkan agar surat bisa dikirim lewat email Anda.",
  },
  no_refresh_token: {
    type: "error",
    text: "Google tidak memberikan izin jangka panjang. Coba hubungkan ulang.",
  },
};

function takeGmailResultFromUrl() {
  let params;
  try {
    params = new URLSearchParams(window.location.search);
  } catch {
    return null;
  }
  const code = params.get("gmail") || params.get("gmail_error");
  if (!code) return null;
  try {
    window.history.replaceState(null, "", window.location.pathname);
  } catch {
    /* biarkan */
  }
  return GMAIL_RESULT_MESSAGE[code] || null;
}

const pendingGmailResult = takeGmailResultFromUrl();

function showAppBanner(type, text) {
  if (!appBanner) return;
  appBanner.className = "app-banner show " + type;
  appBannerText.textContent = text;
  appBanner.hidden = false;
}

function renderGmailStatus(user) {
  if (!topbarGmail) return;
  const connected = !!user.gmail_connected;
  topbarGmail.hidden = false;
  gmailDot.className = "gmail-dot" + (connected ? " on" : "");
  gmailLabel.textContent = connected ? "Gmail terhubung" : "Gmail belum terhubung";
  gmailConnectBtn.hidden = connected;
  gmailDisconnectBtn.hidden = !connected;
}

if (gmailConnectBtn) {
  gmailConnectBtn.addEventListener("click", () => {
    window.location.href = "/auth/gmail/authorize";
  });
}
if (gmailDisconnectBtn) {
  gmailDisconnectBtn.addEventListener("click", async () => {
    gmailDisconnectBtn.disabled = true;
    try {
      await fetch("/auth/gmail/disconnect", { method: "POST" });
      if (currentUser) {
        currentUser.gmail_connected = false;
        renderGmailStatus(currentUser);
      }
      showAppBanner("info", "Koneksi Gmail diputuskan.");
    } catch {
      showAppBanner("error", "Gagal memutuskan koneksi Gmail. Coba lagi.");
    } finally {
      gmailDisconnectBtn.disabled = false;
    }
  });
}
if (document.getElementById("app-banner-close")) {
  document.getElementById("app-banner-close").addEventListener("click", () => {
    appBanner.hidden = true;
  });
}

function renderTopbar(user) {
  topbarName.textContent = user.name || user.email;
  const role = ROLE_LABEL[user.role] || user.role;
  // "Admin · Fakultas Farmasi" untuk admin biasa; cuma "Superadmin" untuk
  // superadmin yang tidak terikat satu unit (unit_name-nya null).
  topbarMeta.textContent = user.unit_name ? `${role} · ${user.unit_name}` : role;
  // Pintu masuk panel kelola unit & admin — hanya superadmin.
  topbarSuperadminBtn.hidden = user.role !== "superadmin";
  renderGmailStatus(user);
  topbar.hidden = false;
}

function showLoginError(message) {
  if (!loginStatus) return;
  loginStatus.className = "status show error";
  loginStatus.textContent = message;
}

/**
 * @param {{ onAuthed: (user) => void, onAnonymous: () => void }} handlers
 */
export async function initAuth({ onAuthed, onAnonymous }) {
  try {
    const res = await fetch("/auth/me");

    if (res.status === 401) {
      currentUser = null;
      topbar.hidden = true;
      if (pendingAuthError) showLoginError(pendingAuthError);
      onAnonymous();
      return null;
    }
    if (!res.ok) {
      throw new Error("Gagal memeriksa status login. Coba muat ulang halaman.");
    }

    currentUser = await res.json();
    renderTopbar(currentUser);
    if (pendingGmailResult) showAppBanner(pendingGmailResult.type, pendingGmailResult.text);
    onAuthed(currentUser);
    return currentUser;
  } catch (err) {
    // Jaringan putus atau respons tak terduga: perlakukan seperti belum
    // login, tapi beri tahu kenapa supaya tidak terlihat seperti app rusak.
    currentUser = null;
    topbar.hidden = true;
    showLoginError(pendingAuthError || err.message || "Tidak bisa menghubungi server.");
    onAnonymous();
    return null;
  }
}
