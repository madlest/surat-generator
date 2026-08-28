from datetime import datetime
from enum import Enum
from sqlalchemy import UniqueConstraint
from sqlmodel import SQLModel, Field, Relationship

from app.models.organization import Unit


class FieldType(str, Enum):
    text = "text"
    date = "date"
    number = "number"
    # Divalidasi & (untuk phone) dinormalisasi di app/services/dynamic_fields.py.
    # Umumnya dipakai pada field manual (from_template=False): alamat tujuan
    # pengiriman surat, bukan variabel di badan docx.
    email = "email"
    phone = "phone"


class FieldLevel(str, Enum):
    batch = "batch"          # sama untuk semua penerima
    recipient = "recipient"  # beda per penerima, jadi kolom form/CSV


class FieldFiller(str, Enum):
    # Diisi admin saat generate (perilaku sekarang, dan default semua field).
    admin = "admin"
    # Diisi pemohon di form publik portal mahasiswa — belum dipakai, disiapkan
    # supaya penambahannya nanti tidak perlu migrasi lagi.
    student = "student"


class LetterType(SQLModel, table=True):
    # Slug hanya wajib unik di dalam satu unit. Fakultas Hukum boleh punya
    # "spm" sendiri tanpa bertabrakan dengan milik Farmasi; itulah sebabnya
    # alamatnya menjadi /generate/{unit_slug}/{slug}.
    __table_args__ = (UniqueConstraint("unit_id", "slug", name="uq_lettertype_unit_slug"),)

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(index=True)  # dipakai di URL, misal "permohonan-mengajar"
    name: str
    template_path: str
    # Wajib: tiap jenis surat dimiliki tepat satu unit. Kolom inilah yang
    # membatasi apa yang boleh dilihat dan disunting seorang admin, sekaligus
    # menjadi dasar pengelompokan di dashboard.
    unit_id: int = Field(foreign_key="unit.id", index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    # Terisi saat jenis surat dihapus. Barisnya sengaja tidak dibuang supaya
    # seluruh konfigurasi field-nya utuh dan pemulihan benar-benar berarti;
    # penghapusan sungguhan dilakukan terpisah lewat halaman arsip.
    deleted_at: datetime | None = Field(default=None)

    unit: Unit = Relationship(back_populates="letter_types")
    fields: list["LetterField"] = Relationship(back_populates="letter_type")


class LetterField(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    letter_type_id: int = Field(foreign_key="lettertype.id")
    field_key: str       # untuk field template: persis sama dg placeholder docx
    label: str            # teks yang ditampilkan di form
    field_type: FieldType = Field(default=FieldType.text)
    level: FieldLevel
    required: bool = Field(default=True)
    display_order: int = Field(default=0)

    # True: field ini berasal dari scan variabel {{ }} di template, ikut
    # dirender ke docx. False: field manual yang dibuat admin (mis. nomor WA /
    # email tujuan) — masuk ke form & CSV, tapi TIDAK diinjeksikan ke context
    # docxtpl. Lihat _format_custom_values di dynamic_batch_generator.py.
    from_template: bool = Field(default=True)

    # Siapa yang mengisi nilai field ini. Semua 'admin' untuk saat ini; kolom
    # ini disiapkan untuk portal mahasiswa (sebagian field jadi 'student').
    filled_by: FieldFiller = Field(default=FieldFiller.admin)

    letter_type: LetterType = Relationship(back_populates="fields")