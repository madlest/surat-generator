# app/services/document_generator.py
import subprocess
import threading
from pathlib import Path

from docxtpl import DocxTemplate

from app.core.config import settings


# Dua proses soffice yang jalan bersamaan memakai profil pengguna yang sama
# saling berebut (yang kedua bisa gagal atau diam-diam menyerahkan kerjanya ke
# yang pertama). Diserialkan lewat lock; batch besar tetap cepat karena satu
# panggilan mengonversi banyak file sekaligus.
_soffice_lock = threading.Lock()


class DocumentGenerationError(Exception):
    """Raised ketika proses isi template atau convert ke PDF gagal."""
    pass


def render_docx(template_path: str, context: dict, output_path: str) -> None:
    """
    Isi template docx dengan context (dict), simpan hasilnya ke output_path.
    Tidak melakukan convert ke PDF — cuma isi template.
    """
    try:
        doc = DocxTemplate(template_path)
        doc.render(context)
        doc.save(output_path)
    except Exception as e:
        raise DocumentGenerationError(
            f"Gagal mengisi template '{template_path}': {e}"
        ) from e


def convert_docx_to_pdf(docx_path: str, output_dir: str) -> str:
    """
    Convert file docx menjadi PDF menggunakan LibreOffice headless.
    PDF hasil disimpan di output_dir, dengan nama file yang sama
    (cuma ekstensi beda), sesuai perilaku default LibreOffice.

    Mengembalikan path lengkap ke file PDF hasil convert.
    """
    with _soffice_lock:
        result = subprocess.run(
            [
                settings.soffice_path,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                docx_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,  # jaga-jaga kalau LibreOffice hang
        )

    if result.returncode != 0:
        raise DocumentGenerationError(
            f"LibreOffice gagal convert '{docx_path}' ke PDF.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )

    # LibreOffice otomatis pakai nama file yang sama, cuma ganti ekstensi
    pdf_filename = Path(docx_path).stem + ".pdf"
    pdf_path = str(Path(output_dir) / pdf_filename)

    if not Path(pdf_path).exists():
        raise DocumentGenerationError(
            f"LibreOffice melapor sukses, tapi file PDF tidak ditemukan di: {pdf_path}"
        )

    return pdf_path


def convert_many_docx_to_pdf(docx_paths: list[str], output_dir: str) -> list[str | None]:
    """
    Convert banyak docx sekaligus dalam SATU proses LibreOffice. Start-up
    LibreOffice memakan sebagian besar waktu per dokumen, jadi satu panggilan
    untuk N file jauh lebih cepat daripada N panggilan (~5x untuk 10 file).

    Mengembalikan list path PDF sejajar dengan docx_paths; entri None berarti
    file itu gagal dikonversi — pemanggil yang menentukan penanganannya.
    """
    if not docx_paths:
        return []

    with _soffice_lock:
        result = subprocess.run(
            [
                settings.soffice_path,
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                *docx_paths,
            ],
            capture_output=True,
            text=True,
            timeout=60 + 10 * len(docx_paths),
        )

    pdf_paths = [str(Path(output_dir) / (Path(p).stem + ".pdf")) for p in docx_paths]
    outputs = [p if Path(p).exists() else None for p in pdf_paths]
    if result.returncode != 0 and not any(outputs):
        raise DocumentGenerationError(
            "LibreOffice gagal convert dokumen ke PDF.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return outputs


def generate_pdf_from_template(
    template_path: str,
    context: dict,
    working_dir: str,
    output_filename_stem: str,
) -> str:
    """
    Fungsi utama yang menggabungkan dua langkah di atas:
    1. Isi template docx dengan context
    2. Convert hasilnya ke PDF

    working_dir: folder kerja sementara (misal temp/job_<uuid>/)
    output_filename_stem: nama file tanpa ekstensi, misal "spm_budi_santoso"

    Mengembalikan path lengkap ke file PDF hasil akhir.
    """
    working_path = Path(working_dir)
    working_path.mkdir(parents=True, exist_ok=True)

    docx_output_path = str(working_path / f"{output_filename_stem}.docx")
    render_docx(template_path, context, docx_output_path)

    pdf_path = convert_docx_to_pdf(docx_output_path, working_dir)

    return pdf_path