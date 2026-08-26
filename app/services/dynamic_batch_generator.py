# Versi generik dari batch_generator.py: bekerja dengan LetterField dinamis
# (dict nilai + definisi field), bukan model Pydantic yang di-hardcode per
# jenis surat. Dipakai oleh semua LetterType, termasuk SPM setelah dimigrasikan.

import zipfile
from datetime import date
from pathlib import Path

from app.core.formatters import (
    build_generic_recipient_filename,
    format_jumlah_lampiran,
    format_tanggal_indonesia,
)
from app.models.letter_type import FieldType, LetterField
from app.services.document_generator import DocumentGenerationError, generate_pdf_from_template
from app.services.pdf_merger import PdfMergeError, merge_pdfs


class DynamicBatchGenerationError(Exception):
    """Raised ketika proses generate satu recipient tertentu gagal."""

    def __init__(self, recipient_index: int, recipient_label: str, original_error: Exception):
        self.recipient_index = recipient_index
        self.recipient_label = recipient_label
        self.original_error = original_error
        super().__init__(
            f"Gagal generate dokumen untuk recipient ke-{recipient_index} "
            f"({recipient_label}): {original_error}"
        )


def _format_custom_values(values: dict, fields: list[LetterField]) -> dict:
    field_types = {field.field_key: field.field_type for field in fields}
    formatted = {}
    for key, value in values.items():
        if field_types.get(key) == FieldType.date and isinstance(value, date):
            formatted[key] = format_tanggal_indonesia(value)
        else:
            formatted[key] = value
    return formatted


def build_context(
    base_info: dict,
    custom_batch_values: dict,
    batch_fields: list[LetterField],
    recipient_values: dict,
    recipient_fields: list[LetterField],
) -> dict:
    """
    Gabungkan field universal (nomor_surat, dst) + field custom batch-level
    + field custom recipient-level jadi satu context dict untuk docxtpl.
    """
    lampirans = base_info["lampirans"]
    context = {
        "nomor_surat": base_info["nomor_surat"],
        "tempat_surat": base_info["tempat_surat"],
        "tanggal_surat": format_tanggal_indonesia(base_info["tanggal_surat"]),
        "perihal_surat": base_info["perihal_surat"],
        "lampirans": lampirans,
        "jumlah_lampiran": len(lampirans),
        "jumlah_lampiran_display": format_jumlah_lampiran(len(lampirans)),
    }
    context.update(_format_custom_values(custom_batch_values, batch_fields))
    context.update(_format_custom_values(recipient_values, recipient_fields))
    return context


def _build_recipient_label(recipient_values: dict, recipient_fields: list[LetterField]) -> str:
    ordered_fields = sorted(recipient_fields, key=lambda f: f.display_order)
    parts = [str(recipient_values[f.field_key]) for f in ordered_fields if recipient_values.get(f.field_key)]
    return " - ".join(parts)


def generate_batch(
    template_path: str,
    base_info: dict,
    custom_batch_values: dict,
    batch_fields: list[LetterField],
    recipients: list[dict],
    recipient_fields: list[LetterField],
    working_dir: str,
    progress_callback=None,
) -> str:
    """
    Generate PDF untuk setiap recipient (cover letter + lampiran tergabung),
    lalu bundling semuanya jadi satu file zip.

    base_info: {nomor_surat, tempat_surat, tanggal_surat (date), perihal_surat,
                lampirans: [{"judul": str, "file_path": str}, ...]}
    """
    working_path = Path(working_dir)
    individual_dir = working_path / "individual"
    individual_dir.mkdir(parents=True, exist_ok=True)

    lampiran_paths = [item["file_path"] for item in base_info["lampirans"] if item.get("file_path")]
    missing = [item["judul"] for item in base_info["lampirans"] if not item.get("file_path")]
    if missing:
        raise DynamicBatchGenerationError(
            recipient_index=-1,
            recipient_label="(semua recipient)",
            original_error=ValueError(
                f"Lampiran berikut belum punya file_path terisi: {', '.join(missing)}"
            ),
        )

    final_pdf_paths: list[str] = []
    used_filenames: dict[str, int] = {}

    for index, recipient_values in enumerate(recipients, start=1):
        label = _build_recipient_label(recipient_values, recipient_fields) or f"Penerima {index}"
        try:
            context = build_context(base_info, custom_batch_values, batch_fields, recipient_values, recipient_fields)

            cover_letter_pdf = generate_pdf_from_template(
                template_path=template_path,
                context=context,
                working_dir=str(working_path / "cover_letters"),
                output_filename_stem=f"cover_{index}",
            )

            filename_stem = build_generic_recipient_filename(label, index)
            used_filenames[filename_stem] = used_filenames.get(filename_stem, 0) + 1
            if used_filenames[filename_stem] > 1:
                filename_stem = f"{filename_stem} ({used_filenames[filename_stem]})"
            final_pdf_path = str(individual_dir / f"{filename_stem}.pdf")

            if progress_callback:
                progress_callback(index, len(recipients))

            merge_pdfs(pdf_paths=[cover_letter_pdf, *lampiran_paths], output_path=final_pdf_path)
            final_pdf_paths.append(final_pdf_path)

        except (DocumentGenerationError, PdfMergeError) as e:
            raise DynamicBatchGenerationError(
                recipient_index=index,
                recipient_label=label,
                original_error=e,
            ) from e

    zip_path = str(working_path / "hasil_batch.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for pdf_path in final_pdf_paths:
            zf.write(pdf_path, arcname=Path(pdf_path).name)

    return zip_path
