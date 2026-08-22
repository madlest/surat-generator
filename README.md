# Surat Generator

Platform untuk generate dan batch-process dokumen surat resmi kampus secara otomatis dari template Word ke PDF — menggantikan alur manual mail merge → export PDF → split → gabung lampiran satu per satu.

Dikembangkan pertama kali untuk Surat Permohonan Mengajar (SPM) di Fakultas Farmasi, namun **arsitekturnya dirancang agar bisa diperluas untuk jenis surat lain** (surat tugas, surat keterangan, surat undangan, dll) maupun **dipakai oleh fakultas/unit lain** yang punya kebutuhan administrasi surat serupa. Setiap jenis surat berjalan sebagai modul independen (template + skema data + endpoint sendiri), sehingga menambah jenis surat baru tidak memerlukan perubahan pada logic inti (isi template, konversi PDF, penggabungan lampiran, batch processing).

Dibangun dengan Python 3.12, FastAPI, dan `docxtpl`, sebagai proyek belajar sekaligus alat bantu administrasi yang berkembang sesuai kebutuhan nyata di lapangan.

## Fitur

- **Generate surat dari template Word** — isi data (nomor surat, tanggal, pihak terkait, perihal, dst) lewat form, hasilnya dokumen PDF sesuai format resmi institusi.
- **Batch generation** — satu surat, banyak penerima. Input daftar penerima bisa lewat form langsung atau upload CSV; setiap penerima otomatis dapat satu PDF gabungan (surat + lampiran).
- **Lampiran dinamis** — upload beberapa file lampiran sekaligus (judul + file PDF), otomatis tergabung ke setiap dokumen hasil generate dan tercantum sebagai daftar lampiran di badan surat.
- **Output dalam ZIP** — semua dokumen hasil batch dibundel jadi satu file ZIP untuk diunduh sekaligus.
- **Format tanggal Indonesia otomatis** — tanggal ditampilkan dalam format lokal (mis. "21 Agustus 2026") tanpa perlu input manual.
- **Dirancang untuk berkembang** — logic inti (`services/`) bersifat generik dan tidak terikat ke satu jenis surat; menambah jenis surat baru cukup dengan menambah template docx, skema data (model), dan endpoint baru mengikuti pola yang sudah ada.

## Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12)
- **Package manager**: [uv](https://github.com/astral-sh/uv)
- **Template engine dokumen**: [docxtpl](https://docxtpl.readthedocs.io/) (Jinja2 untuk file `.docx`)
- **Konversi DOCX → PDF**: [LibreOffice](https://www.libreoffice.org/) (headless mode)
- **Penggabungan PDF**: [pypdf](https://pypdf.readthedocs.io/)
- **Validasi data**: [Pydantic](https://docs.pydantic.dev/)

## Prasyarat

- Python 3.12
- [uv](https://github.com/astral-sh/uv) sudah terinstall
- LibreOffice terinstall dan command `soffice` dapat diakses dari terminal
  ```bash
  sudo apt install libreoffice
  ```
- Locale Bahasa Indonesia terinstall di sistem (dibutuhkan untuk format tanggal)
  ```bash
  sudo locale-gen id_ID.UTF-8
  sudo update-locale
  ```

## Instalasi

```bash
git clone <url-repo-ini>
cd surat-generator

# install dependency (otomatis membuat virtual environment)
uv sync
```

## Menjalankan Aplikasi

```bash
uv run uvicorn app.main:app --reload
```

Aplikasi akan berjalan di `http://localhost:8000`. Dokumentasi API interaktif (Swagger UI) tersedia di `http://localhost:8000/docs`.

## Struktur Proyek

```
app/
├── main.py              # entry point FastAPI
├── core/                # konfigurasi, locale, formatter
├── models/               # skema data (Pydantic), satu file per jenis surat
├── routers/              # endpoint HTTP, satu file per jenis surat
├── services/             # logic inti generik: parsing, generate dokumen, gabung PDF, batch
├── templates/            # file template .docx, satu file per jenis surat
└── static/               # (opsional) frontend sederhana
```

## Menambahkan Jenis Surat Baru

Proyek ini sengaja dirancang agar satu jenis surat = satu "paket" (template + model + router) yang berdiri sendiri, sementara logic inti di `services/` dipakai bersama oleh semua jenis surat. Untuk menambah jenis surat baru:

1. Siapkan file template `.docx` dengan placeholder `docxtpl` (`{{ }}`), simpan di `templates/`.
2. Buat skema data (Pydantic model) di `models/`, mewarisi field umum dari `SuratBase` (nomor surat, tanggal, perihal) dan menambahkan field spesifik jenis surat tersebut.
3. Buat endpoint baru di `routers/` yang memanggil service generik yang sudah ada (`document_generator`, `pdf_merger`, `batch_generator`) dengan template dan model yang baru dibuat.

Logic inti tidak perlu diubah — ini yang membuat proyek tetap scalable untuk kebutuhan surat-menyurat yang terus berkembang, baik di Fakultas Farmasi maupun unit lain yang ingin mengadopsi.

## Status Pengembangan

Proyek ini masih dalam tahap pengembangan aktif sebagai bagian dari proses belajar FastAPI dan otomasi dokumen. Fitur inti (generate dokumen, batch processing, penggabungan lampiran) sudah berfungsi dan teruji; endpoint API dan antarmuka pengguna masih dalam proses penyelesaian.

## Lisensi

Belum ditentukan.

## Credits

Proyek ini dikembangkan dengan bantuan [Claude](https://claude.ai) (Anthropic) sebagai pair-programming partner — mulai dari diskusi arsitektur, penulisan kode, hingga proses debugging dan belajar konsep-konsep baru (FastAPI, Pydantic, docxtpl, dsb) sepanjang pengembangan.