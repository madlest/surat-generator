#Field yang digunakan untuk membuat surat secara umum
from datetime import date
from pydantic import BaseModel, Field, computed_field
from app.core.formatters import format_tanggal_indonesia, format_jumlah_lampiran

class LampiranItem(BaseModel):
    judul: str = Field(min_length=1)
    file_path: str | None = None


class SuratBase(BaseModel):
    nomor_surat: str
    tempat_surat: str
    tanggal_surat: date
    perihal_surat: str
    lampirans: list[LampiranItem] = Field(default_factory=list)

    @computed_field
    @property
    def tanggal_surat_formatted(self) -> str:
        return format_tanggal_indonesia(self.tanggal_surat)
    
    @computed_field
    @property
    def jumlah_lampiran(self) -> int:
        return len(self.lampirans)

    @computed_field
    @property
    def jumlah_lampiran_display(self) -> str:
        return format_jumlah_lampiran(len(self.lampirans))