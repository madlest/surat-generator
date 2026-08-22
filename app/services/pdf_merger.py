# Fungsi untuk menggabungkan beberapa file PDF menjadi satu file PDF.
from pathlib import Path

from pypdf import PdfWriter


class PdfMergeError(Exception):
    """Raised ketika proses menggabungkan PDF gagal."""
    pass


def merge_pdfs(pdf_paths: list[str], output_path: str) -> str:
    """
    Gabungkan beberapa file PDF jadi satu file PDF, sesuai urutan
    yang diberikan di pdf_paths (index pertama jadi halaman paling awal).

    pdf_paths: list path PDF, urutan pertama biasanya cover letter
               (hasil dari document_generator), diikuti lampiran-lampiran
               sesuai urutannya masing-masing.
    output_path: path lengkap file PDF hasil gabungan.

    Mengembalikan path ke file PDF hasil gabungan.
    """
    if not pdf_paths:
        raise PdfMergeError("Tidak ada file PDF yang diberikan untuk digabung.")

    writer = PdfWriter()

    for pdf_path in pdf_paths:
        if not Path(pdf_path).exists():
            raise PdfMergeError(f"File PDF tidak ditemukan: {pdf_path}")
        try:
            writer.append(pdf_path)
        except Exception as e:
            raise PdfMergeError(
                f"Gagal membaca/menggabungkan file '{pdf_path}': {e}"
            ) from e

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(output_path, "wb") as f:
            writer.write(f)
    except Exception as e:
        raise PdfMergeError(f"Gagal menyimpan hasil gabungan ke '{output_path}': {e}") from e
    finally:
        writer.close()

    return output_path