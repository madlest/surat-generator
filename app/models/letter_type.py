from datetime import datetime
from enum import Enum
from sqlmodel import SQLModel, Field, Relationship


class FieldType(str, Enum):
    text = "text"
    date = "date"
    number = "number"


class FieldLevel(str, Enum):
    batch = "batch"          # sama untuk semua penerima
    recipient = "recipient"  # beda per penerima, jadi kolom form/CSV


class LetterType(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)  # dipakai di URL, misal "permohonan-mengajar"
    name: str
    template_path: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Terisi saat jenis surat dihapus. Barisnya sengaja tidak dibuang supaya
    # seluruh konfigurasi field-nya utuh dan pemulihan benar-benar berarti;
    # penghapusan sungguhan dilakukan terpisah lewat halaman arsip.
    deleted_at: datetime | None = Field(default=None)

    fields: list["LetterField"] = Relationship(back_populates="letter_type")


class LetterField(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    letter_type_id: int = Field(foreign_key="lettertype.id")
    field_key: str       # harus persis sama dengan nama placeholder di docx
    label: str            # teks yang ditampilkan di form
    field_type: FieldType = Field(default=FieldType.text)
    level: FieldLevel
    required: bool = Field(default=True)
    display_order: int = Field(default=0)

    letter_type: LetterType = Relationship(back_populates="fields")