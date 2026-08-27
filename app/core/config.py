import locale
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')
except locale.Error:
    raise RuntimeError(
        "Locale 'id_ID.UTF-8' belum terinstall di sistem ini. "
        "Jalankan: sudo locale-gen id_ID.UTF-8 && sudo update-locale"
    )
    
class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    soffice_path: str = "soffice" 
    temp_dir: str = "temp"

    # OAuth 2.0 "External" (lihat catatan keputusan v2.0.0): karena akses
    # Google Cloud Platform dinonaktifkan admin Workspace kampus, tipe
    # "Internal" tidak tersedia. Pembatasan ke domain @umbjm.ac.id karena itu
    # dilakukan sendiri di app/core/oauth.py, bukan diserahkan ke Google.
    google_client_id: str = ""
    google_client_secret: str = ""

    # Kunci penandatanganan cookie sesi (itsdangerous) dan token state OAuth.
    # HARUS diisi nilai acak panjang di .env produksi — nilai default di
    # sini cuma supaya app tidak crash saat belum dikonfigurasi di dev awal.
    session_secret_key: str = "ganti-nilai-ini-di-env-produksi"

    # Daftar email yang di-bootstrap otomatis jadi superadmin pada login
    # pertama mereka, walau belum ada baris User yang dibuat manual lebih
    # dulu. Dipisah koma, misal: "tri@umbjm.ac.id,rekan@umbjm.ac.id"
    superadmin_emails: str = ""

    @property
    def superadmin_email_list(self) -> list[str]:
        return [e.strip().lower() for e in self.superadmin_emails.split(",") if e.strip()]


settings = Settings()