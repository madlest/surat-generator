# Template data model untuk permohonan mengajar batch (multiple recipients) yang akan diisi oleh user.

from datetime import date
from pydantic import BaseModel, Field, computed_field
from .base import SuratBase
from app.core.formatters import format_tanggal_indonesia

class PermohonanMengajarBatchInfo(SuratBase):
    program_studi: str = Field(min_length=1)
    tahun_akademik: str
    tanggal_mulai_perkuliahan: date
    
    @computed_field
    @property
    def tanggal_mulai_perkuliahan_formatted(self) -> str:
        
        return format_tanggal_indonesia(self.tanggal_mulai_perkuliahan)
        

class PermohonanMengajarRecipient(BaseModel):
    nama_dosen: str = Field(min_length=1)
    mata_kuliah: str = Field(min_length=1)
    semester: str = Field(min_length=1)


class PermohonanMengajarRequest(BaseModel):
    batch_info: PermohonanMengajarBatchInfo
    recipients: list[PermohonanMengajarRecipient]