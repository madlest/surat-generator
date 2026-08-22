#Field yang digunakan untuk membuat surat secara umum
from datetime import date
from pydantic import BaseModel, computed_field

from app.core.formatters import format_tanggal_indonesia


class SuratBase(BaseModel):
    nomor_surat: str
    tempat_surat: str
    tanggal_surat: date
    perihal_surat: str

    @computed_field
    @property
    def tanggal_surat_formatted(self) -> str:
        return format_tanggal_indonesia(self.tanggal_surat)