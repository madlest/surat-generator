# Fungsi untuk generate batch dokumen (cover letter + lampiran) untuk permohonan mengajar.

import zipfile
from pathlib import Path

from app.core.formatters import build_recipient_filename
from app.models.permohonan_mengajar import (
    PermohonanMengajarBatchInfo,
    PermohonanMengajarRecipient,
)
from app.services.document_generator import (
    DocumentGenerationError,
    generate_pdf_from_template,
)
from app.services.pdf_merger import PdfMergeError, merge_pdfs


class BatchGenerationError(Exception):
    """Raised ketika proses generate satu recipient tertentu gagal."""
    def __init__(self, recipient_index: int, nama_dosen: str, original_error: Exception):
        self.recipient_index = recipient_index
        self.nama_dosen = nama_dosen
        self.original_error = original_error
        super().__init__(
            f"Gagal generate dokumen untuk recipient ke-{recipient_index} "
            f"({nama_dosen}): {original_error}"
        )


def _build_context(
    batch_info: PermohonanMengajarBatchInfo,
    recipient: PermohonanMengajarRecipient,
) -> dict:
    """
    Gabungkan batch_info + satu recipient jadi satu context dict
    untuk docxtpl, dengan tanggal sudah dalam bentuk formatted string.
    """
    return {
        **batch_info.model_dump(),
        **recipient.model_dump(),
        "tanggal_surat": batch_info.tanggal_surat_formatted,
        "tanggal_mulai_perkuliahan": batch_info.tanggal_mulai_perkuliahan_formatted,
    }


def generate_batch(
    template_path: str,
    batch_info: PermohonanMengajarBatchInfo,
    recipients: list[PermohonanMengajarRecipient],
    working_dir: str,
) -> str:
    """
    Generate PDF untuk setiap recipient (cover letter + lampiran tergabung),
    lalu bundling semuanya jadi satu file zip.

    Asumsi penting: setiap LampiranItem di batch_info.lampirans SUDAH
    punya file_path terisi (menunjuk ke file PDF lampiran yang sudah
    disimpan sebelumnya oleh caller/router) — fungsi ini tidak menangani
    proses upload file, hanya membaca path yang sudah ada.

    working_dir: folder kerja untuk batch ini (misal temp/job_<uuid>/).
    Di dalamnya akan dibuat subfolder 'individual/' (PDF per recipient
    sebelum di-zip) dan file zip akhir akan diletakkan langsung di
    working_dir.

    Mengembalikan path ke file zip hasil akhir.
    """
    working_path = Path(working_dir)
    individual_dir = working_path / "individual"
    individual_dir.mkdir(parents=True, exist_ok=True)

    lampiran_paths = [item.file_path for item in batch_info.lampirans]
    missing = [
        item.judul for item in batch_info.lampirans if not item.file_path
    ]
    if missing:
        raise BatchGenerationError(
            recipient_index=-1,
            nama_dosen="(semua recipient)",
            original_error=ValueError(
                f"Lampiran berikut belum punya file_path terisi: {', '.join(missing)}"
            ),
        )

    final_pdf_paths: list[str] = []

    for index, recipient in enumerate(recipients, start=1):
        try:
            context = _build_context(batch_info, recipient)

            # cover letter untuk recipient ini, disimpan dengan nama unik
            # berbasis index supaya tidak tabrakan antar recipient
            cover_letter_pdf = generate_pdf_from_template(
                template_path=template_path,
                context=context,
                working_dir=str(working_path / "cover_letters"),
                output_filename_stem=f"cover_{index}",
            )

            final_filename = build_recipient_filename(
                nama_dosen=recipient.nama_dosen,
                mata_kuliah=recipient.mata_kuliah,
                semester=recipient.semester,
            )
            final_pdf_path = str(individual_dir / final_filename)

            merge_pdfs(
                pdf_paths=[cover_letter_pdf, *lampiran_paths],
                output_path=final_pdf_path,
            )

            final_pdf_paths.append(final_pdf_path)

        except (DocumentGenerationError, PdfMergeError) as e:
            raise BatchGenerationError(
                recipient_index=index,
                nama_dosen=recipient.nama_dosen,
                original_error=e,
            ) from e

    zip_path = str(working_path / "hasil_batch.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_path in final_pdf_paths:
            zf.write(pdf_path, arcname=Path(pdf_path).name)

    return zip_path