from docxtpl import DocxTemplate

BASE_RESERVED_NAMES = {
    "nomor_surat",
    "tempat_surat",
    "tanggal_surat",
    "tanggal_surat_formatted",
    "perihal_surat",
    "lampirans",
    "jumlah_lampiran",
    "jumlah_lampiran_display",
}


class TemplateInspectionError(Exception):
    pass


def detect_custom_variables(docx_path: str) -> list[str]:
    try:
        doc = DocxTemplate(docx_path)
        all_vars = doc.get_undeclared_template_variables()
    except Exception as e:
        raise TemplateInspectionError(f"Gagal membaca template: {e}") from e

    return sorted(v for v in all_vars if v not in BASE_RESERVED_NAMES)