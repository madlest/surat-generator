# Surat Generator

Platform untuk membuat dan batch-process dokumen surat resmi kampus dari template Word ke PDF — menggantikan alur manual mail merge → export PDF → split → gabung lampiran satu per satu.

Awalnya dibangun untuk Surat Permohonan Mengajar (SPM) di Fakultas Farmasi, Universitas Muhammadiyah Banjarmasin. Sejak v1.1.0, aplikasi **tidak lagi terikat ke satu jenis surat**: admin bisa menambahkan jenis surat baru langsung dari dashboard — cukup unggah template `.docx`, tanpa menyentuh kode sama sekali. Sejak v2.0.0, aplikasi **dapat melayani banyak unit kerja** (fakultas, biro, rektorat) dengan login Google dan pembagian peran per unit.

Dibangun dengan Python 3.12 dan FastAPI, sebagai proyek belajar sekaligus alat bantu administrasi yang berkembang mengikuti kebutuhan nyata di lapangan.

**Produksi**: https://surat-generator.duckdns.org/

## Fitur

- **Login Google & peran per unit** — akses berbasis **daftar undangan**, bukan pendaftaran terbuka: seseorang baru bisa masuk setelah emailnya (`@umbjm.ac.id`) didaftarkan oleh superadmin. Dua peran: **superadmin** (melihat semua unit, mendaftarkan unit baru, mengundang/mencabut admin) dan **admin** (dibatasi ke jenis surat milik unitnya sendiri). Sesi memakai cookie bertanda tangan (stateless); pencabutan akses berlaku instan.
- **Multi-unit** — jenis surat dimiliki oleh satu **unit** (fakultas, biro, rektorat, dst). Slug jenis surat cukup unik per unit, dan alamat generate menjadi `/generate/{unit_slug}/{slug}`. Dashboard mengelompokkan jenis surat per unit untuk superadmin.
- **Jenis surat dinamis** — admin menambah jenis surat baru lewat wizard: unggah template `.docx`, variabel Jinja di dalamnya terdeteksi otomatis, lalu admin mengatur label, tipe (teks/tanggal/angka), level tiap field (`batch` = sekali per surat, `recipient` = per penerima), dan **urutan tampilnya** (seret-urutkan langsung di wizard). Jenis surat juga bisa diubah (termasuk ganti slug dan template) atau dihapus.
- **Unduh template aktif** — saat mengubah jenis surat, admin bisa mengunduh salinan template `.docx` yang sedang dipakai, sebagai berkas dasar untuk revisi.
- **Hapus lunak & arsip** — jenis surat yang dihapus masuk ke arsip lengkap dengan konfigurasi fieldnya, bisa dipulihkan utuh kapan saja atau dihapus permanen.
- **Generate & batch generation** — isi data lewat form dinamis atau upload CSV; satu surat bisa dikirim ke banyak penerima sekaligus, dengan progress yang bisa dipantau (polling).
- **Preview sebelum unduh** — generate dokumen untuk penerima pertama saja (termasuk lampiran tergabung) untuk diperiksa, tanpa perlu memproses seluruh batch dulu.
- **Lampiran dinamis** — gabungkan beberapa file PDF lampiran ke setiap dokumen hasil generate.
- **Output dalam ZIP** — seluruh dokumen hasil batch dibundel jadi satu file ZIP untuk diunduh sekaligus.
- **Format tanggal Indonesia** — seragam `DD-MM-YYYY` di seluruh antarmuka, dengan konversi otomatis dari input CSV.
- **Frontend ringan** — modul ES per fitur (`app/static/js/`), tanpa build step.

## Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12)
- **Package manager**: [uv](https://github.com/astral-sh/uv)
- **Database & ORM**: [SQLModel](https://sqlmodel.tiangolo.com/), migrasi skema dengan [Alembic](https://alembic.sqlalchemy.org/)
- **Autentikasi**: Google OAuth 2.0 ([google-auth](https://google-auth.readthedocs.io/)), sesi cookie bertanda tangan dengan [itsdangerous](https://itsdangerous.palletsprojects.com/)
- **Template engine dokumen**: [docxtpl](https://docxtpl.readthedocs.io/) (Jinja2 untuk file `.docx`)
- **Konversi DOCX → PDF**: [LibreOffice](https://www.libreoffice.org/) (headless mode)
- **Penggabungan PDF**: [pypdf](https://pypdf.readthedocs.io/)
- **Validasi & konfigurasi**: [Pydantic](https://docs.pydantic.dev/) / [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- **Frontend**: HTML/CSS/JS statis, tanpa framework atau build step

## Prasyarat

- Python 3.12
- [uv](https://github.com/astral-sh/uv) sudah terinstall
- LibreOffice terinstall dan command `soffice` dapat diakses dari terminal
  ```bash
  sudo apt install libreoffice
  ```
- Locale Bahasa Indonesia terinstall di sistem (aplikasi akan menolak jalan tanpanya)
  ```bash
  sudo locale-gen id_ID.UTF-8
  sudo update-locale
  ```

## Instalasi

```bash
git clone https://github.com/madlest/surat-generator.git
cd surat-generator

# install dependency (otomatis membuat virtual environment)
uv sync

# siapkan skema database
uv run alembic upgrade head
```

### Konfigurasi (`.env`)

Buat file `.env` di root proyek:

```dotenv
# Konversi DOCX -> PDF
SOFFICE_PATH=soffice

# OAuth 2.0 — lihat catatan setup di bawah
GOOGLE_CLIENT_ID=xxxxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=xxxxx

# Kunci penandatanganan cookie sesi — WAJIB nilai acak panjang di produksi
SESSION_SECRET_KEY=ganti-dengan-hasil-openssl-rand-hex-32

# Email yang otomatis jadi superadmin pada login pertamanya (dipisah koma).
# Menyelesaikan masalah ayam-telur "siapa yang mengundang superadmin pertama".
SUPERADMIN_EMAILS=nama@umbjm.ac.id

# Kunci Fernet untuk mengenkripsi refresh token Gmail admin (fitur kirim surat
# via email). Opsional — kosongkan kalau fitur email belum dipakai. Bikin:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# JANGAN diganti setelah ada admin yang menghubungkan Gmail.
EMAIL_TOKEN_KEY=
```

**OAuth Google:** buat OAuth Client (tipe *Web application*) di [Google Cloud Console](https://console.cloud.google.com/apis/credentials). Daftarkan **Authorized redirect URI** sesuai tempat aplikasi berjalan:

- lokal: `http://localhost:8000/auth/callback`
- produksi: `https://<domain-anda>/auth/callback`

Consent screen boleh bertipe **External** — pembatasan ke domain `@umbjm.ac.id` dilakukan di dalam kode (memeriksa `email_verified` dan akhiran email), bukan mengandalkan tipe "Internal".

## Menjalankan Aplikasi

```bash
uv run uvicorn app.main:app --reload
```

Aplikasi berjalan di `http://localhost:8000`. Dokumentasi API interaktif (Swagger UI) tersedia di `http://localhost:8000/docs`.

Login pertama memakai salah satu email di `SUPERADMIN_EMAILS` — akun itu otomatis dibuat sebagai superadmin. Dari panel "Kelola Unit & Admin", superadmin mendaftarkan unit dan mengundang admin lain.

## Menjalankan Test

```bash
uv run pytest -q
```

## Struktur Proyek

```
app/
├── main.py                  # entry point FastAPI
├── core/                    # konfigurasi, database, locale, formatter,
│                              #   security (cookie sesi), oauth (verifikasi token Google)
├── dependencies.py          # dependency otorisasi: get_current_user, require_superadmin,
│                              #   scope_unit_id
├── models/                  # skema data (SQLModel): LetterType, LetterField,
│                              #   Unit, User (organization.py)
├── routers/
│   ├── auth.py               # /auth/login, /auth/callback, /auth/logout, /auth/me
│   ├── superadmin.py         # kelola unit + undang/cabut admin (khusus superadmin)
│   ├── admin.py              # CRUD jenis surat, wizard deteksi field, arsip (di-scope per unit)
│   └── generate.py           # generate & batch generate surat
├── services/                 # logic inti: inspeksi template, parsing field,
│                              #   generate dokumen, gabung PDF, batch, job status
├── templates/uploaded/       # template .docx aktif, per unit: {unit_slug}/{slug}.docx
│                              #   (di-gitignore, jangan dihapus)
└── static/
    ├── index.html
    ├── css/style.css
    └── js/                    # modul ES per fitur (auth, admin, superadmin, form, dashboard, dst)

migrations/                  # migrasi skema database (Alembic)
tests/                       # pytest (TestClient + SQLite in-memory)
```

## Autentikasi & Peran

- **Login = daftar undangan.** Punya email `@umbjm.ac.id` saja tidak cukup (mahasiswa pun punya) — baris `User` dibuat lebih dulu oleh superadmin, baru orangnya bisa masuk. Nama/foto terisi otomatis saat login pertama.
- **`superadmin`** — tidak terikat satu unit. Melihat dan mengelola semua unit, mendaftarkan unit baru, mengundang dan menonaktifkan admin. Tidak bisa menonaktifkan satu-satunya superadmin aktif yang tersisa.
- **`admin`** — dibatasi ke `unit_id` miliknya. Jenis surat unit lain tampil seolah tidak ada (respons 404, bukan 403). Tidak ada akses lintas unit sekalipun read-only.
- **Sesi** memakai cookie bertanda tangan (stateless, tanpa tabel session). Pencabutan akses (`is_active = false`) berlaku pada request berikutnya.
- **Slug unit permanen** setelah dibuat (dipakai sebagai nama folder template dan di URL). Nama unit bisa diubah; unit hanya bisa dihapus kalau benar-benar kosong.

## Menambahkan Jenis Surat Baru

Sejak v1.1.0, menambah jenis surat **tidak lagi memerlukan perubahan kode**. Semua dilakukan lewat dashboard admin:

1. Buka wizard "Tambah Jenis Surat" dan unggah file template `.docx` (memakai placeholder Jinja `{{ }}` ala `docxtpl`). Superadmin memilih unit pemilik; admin biasa otomatis memakai unitnya.
2. Variabel dalam template terdeteksi otomatis. Untuk tiap variabel, atur label yang ditampilkan, tipe data (teks/tanggal/angka), level (`batch` sekali per surat atau `recipient` beda-beda per penerima), dan urutan tampil (seret baris field-nya sesuai kebutuhan).
3. Simpan — jenis surat baru langsung muncul di dashboard dan siap dipakai untuk generate/batch generate.

Jenis surat yang sudah ada juga bisa diubah (termasuk ganti template — dengan opsi mengunduh dulu template yang sedang aktif sebagai berkas dasar revisi) lewat wizard yang sama, atau dihapus (masuk arsip, bisa dipulihkan).

## Status Pengembangan

**v1.1.0** — dirilis dan berjalan di produksi. Wizard jenis surat dinamis, dashboard, batch generation, lampiran, arsip/hapus lunak, dan migrasi skema database (Alembic) sudah lengkap dan teruji.

**v1.2.0** — dirilis. Seret-urutkan field di wizard admin, preview dokumen sebelum unduh (satu penerima pertama, termasuk lampiran), dan unduh template `.docx` yang sedang aktif.

**v2.0.0** — login Google OAuth (akses berbasis undangan, validasi domain `@umbjm.ac.id`), peran superadmin/admin, dan kepemilikan jenis surat per **unit** (fakultas/biro/rektorat). Termasuk panel superadmin untuk kelola unit dan undang/cabut admin, penataan template per unit (`{unit_slug}/{slug}.docx`), dan dashboard yang dikelompokkan per unit.

Rencana berikutnya (belum dijadwalkan): admin multi-unit (satu orang mengelola lebih dari satu unit), pengelompokan jenis surat ke dalam section, dan pengiriman massal ke penerima (email dan/atau WhatsApp, sebagai dua kapabilitas terpisah yang bisa hidup berdampingan per jenis surat).

## Lisensi

[MIT](LICENSE)

## Credits

Proyek ini dikembangkan dengan bantuan [Claude](https://claude.ai) (Anthropic) sebagai pair-programming partner — mulai dari diskusi arsitektur, penulisan kode, hingga proses debugging dan belajar konsep-konsep baru (FastAPI, SQLModel, Alembic, docxtpl, dsb) sepanjang pengembangan.
