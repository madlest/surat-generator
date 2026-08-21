# Field yang digunakan untuk membuat surat permohonan mengajar
from datetime import date
from pydantic import BaseModel, Field, computed_field
from .base import SuratBase

class PermohonanMengajarBatchInfo(SuratBase):
    tahun_akademik: str
    tanggal_mulai_perkuliahan: date
    lampirans: list[str]

    @computed_field
    @property
    def jumlah_lampiran(self) -> int:
        return len(self.lampirans)

class PermohonanMengajarRecipient(BaseModel):
    nama_dosen: str = Field(min_length=1)
    mata_kuliah: str = Field(min_length=1)
    semester: str = Field(min_length=1)

class PermohonanMengajarRequest(BaseModel):
    batch_info: PermohonanMengajarBatchInfo
    recipients: list[PermohonanMengajarRecipient]