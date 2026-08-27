# Surat Generator

Platform untuk membuat dan batch-process dokumen surat resmi kampus dari template Word ke PDF — menggantikan alur manual mail merge → export PDF → split → gabung lampiran satu per satu.

Awalnya dibangun untuk Surat Permohonan Mengajar (SPM) di Fakultas Farmasi, Universitas Muhammadiyah Banjarmasin. Sejak v1.1.0, aplikasi **tidak lagi terikat ke satu jenis surat**: admin bisa menambahkan jenis surat baru langsung dari dashboard — cukup unggah template `.docx`, tanpa menyentuh kode sama sekali.

Dibangun dengan Python 3.12 dan FastAPI, sebagai proyek belajar sekaligus alat bantu administrasi yang berkembang mengikuti kebutuhan nyata di lapangan.

**Produksi**: https://surat-generator.duckdns.org/

## Fitur

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

## Menjalankan Aplikasi

```bash
uv run uvicorn app.main:app --reload
```

Aplikasi berjalan di `http://localhost:8000`. Dokumentasi API interaktif (Swagger UI) tersedia di `http://localhost:8000/docs`.

## Struktur Proyek

```
app/
├── main.py                  # entry point FastAPI
├── core/                    # konfigurasi, koneksi database, locale, formatter
├── models/                  # skema data (SQLModel): LetterType, LetterField
├── routers/
│   ├── admin.py              # CRUD jenis surat, wizard deteksi field, arsip
│   └── generate.py           # generate & batch generate surat
├── services/                 # logic inti: inspeksi template, parsing field,
│                              #   generate dokumen, gabung PDF, batch, job status
├── templates/uploaded/       # template .docx aktif (di-gitignore, jangan dihapus)
└── static/
    ├── index.html
    ├── css/style.css
    └── js/                    # modul ES per fitur (admin, form, dashboard, archive, dst)

migrations/                  # migrasi skema database (Alembic)
```

## Menambahkan Jenis Surat Baru

Sejak v1.1.0, menambah jenis surat **tidak lagi memerlukan perubahan kode**. Semua dilakukan lewat dashboard admin:

1. Buka wizard "Tambah Jenis Surat" dan unggah file template `.docx` (memakai placeholder Jinja `{{ }}` ala `docxtpl`).
2. Variabel dalam template terdeteksi otomatis. Untuk tiap variabel, atur label yang ditampilkan, tipe data (teks/tanggal/angka), level (`batch` sekali per surat atau `recipient` beda-beda per penerima), dan urutan tampil (seret baris field-nya sesuai kebutuhan).
3. Simpan — jenis surat baru langsung muncul di dashboard dan siap dipakai untuk generate/batch generate.

Jenis surat yang sudah ada juga bisa diubah (termasuk ganti template — dengan opsi mengunduh dulu template yang sedang aktif sebagai berkas dasar revisi) lewat wizard yang sama, atau dihapus (masuk arsip, bisa dipulihkan).

## Status Pengembangan

**v1.1.0** — dirilis dan berjalan di produksi. Wizard jenis surat dinamis, dashboard, batch generation, lampiran, arsip/hapus lunak, dan migrasi skema database (Alembic) sudah lengkap dan teruji.

**v1.2.0** — dirilis. Seret-urutkan field di wizard admin, preview dokumen sebelum unduh (satu penerima pertama, termasuk lampiran), dan unduh template `.docx` yang sedang aktif.

Rencana berikutnya (belum dijadwalkan): pengelompokan jenis surat ke dalam section, dan pengiriman massal ke penerima (email dan/atau WhatsApp, sebagai dua kapabilitas terpisah yang bisa hidup berdampingan per jenis surat).

## Lisensi

[MIT](LICENSE)

## Credits

Proyek ini dikembangkan dengan bantuan [Claude](https://claude.ai) (Anthropic) sebagai pair-programming partner — mulai dari diskusi arsitektur, penulisan kode, hingga proses debugging dan belajar konsep-konsep baru (FastAPI, SQLModel, Alembic, docxtpl, dsb) sepanjang pengembangan.
