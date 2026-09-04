from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    # Hanya untuk type checker. Impor sungguhan di sini akan melingkar, karena
    # letter_type.py sendiri perlu mengimpor Unit. SQLAlchemy sanggup
    # meresolusi "LetterType" dari nama kelasnya saat mapper dikonfigurasi,
    # asalkan modulnya sudah pernah diimpor — dan letter_type.py selalu ikut
    # terimpor, karena ia sendiri yang mengimpor modul ini.
    from app.models.letter_type import LetterType


class UserRole(str, Enum):
    # Melihat dan mengelola seluruh unit, termasuk mendaftarkan unit baru dan
    # mengundang admin.
    superadmin = "superadmin"
    # Terbatas pada jenis surat milik unitnya sendiri.
    admin = "admin"


class Unit(SQLModel, table=True):
    """
    Satuan kerja pemilik jenis surat.

    Sengaja tidak dinamai Faculty: pemakainya tidak hanya fakultas, tapi juga
    unit tingkat universitas seperti rektorat, kemahasiswaan, dan SDM. Sebutan
    aslinya disimpan apa adanya di `name` ("Fakultas Farmasi", "Biro SDM"),
    jadi tampilan tetap wajar tanpa memaksa istilah "unit" ke muka pengguna.

    Belum ada hierarki di sini. Kalau kelak prodi perlu dipisah, tinggal
    ditambah parent_id yang menunjuk ke tabel ini sendiri.
    """

    id: int | None = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)  # dipakai di URL, misal "hukum"
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    users: list["User"] = Relationship(back_populates="unit")
    letter_types: list["LetterType"] = Relationship(back_populates="unit")


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)

    # Email adalah identitas utamanya, bukan id internal: superadmin mengundang
    # orang dengan mengetik emailnya, jadi barisnya sudah ada sebelum yang
    # bersangkutan pernah login. Pencocokan dengan akun Google terjadi di sini.
    # Konsekuensinya login bersifat daftar-undangan, bukan pendaftaran terbuka
    # — punya email @umbjm.ac.id saja tidak cukup, dan itu memang disengaja
    # karena mahasiswa pun memakai domain yang sama.
    email: str = Field(unique=True, index=True)

    # Tiga kolom berikut baru terisi saat login pertama, diambil dari ID token
    # Google. Karena itu nullable — pada baris hasil undangan semuanya kosong.
    name: str | None = Field(default=None)
    picture_url: str | None = Field(default=None)
    last_login_at: datetime | None = Field(default=None)

    role: UserRole = Field(default=UserRole.admin)

    # Kosong untuk superadmin, yang memang tidak terikat satu unit.
    unit_id: int | None = Field(default=None, foreign_key="unit.id", index=True)

    # Mencabut akses tanpa menghapus barisnya, supaya undangan lama tidak perlu
    # diketik ulang kalau orangnya kembali.
    is_active: bool = Field(default=True)

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Refresh token OAuth Gmail milik admin ini, TERENKRIPSI (Fernet, lihat
    # app/core/crypto.py). Terisi saat admin menekan "Hubungkan Gmail" dan
    # menyetujui scope gmail.send; None = belum terhubung. Email dikirim
    # sebagai user.email — tidak ada alamat "from" terpisah. Sengaja dipisah
    # dari alur login utama supaya admin yang tak pernah kirim surat tidak
    # kena consent screen scope sensitif.
    gmail_refresh_token_enc: str | None = Field(default=None)
    gmail_connected_at: datetime | None = Field(default=None)

    unit: Unit | None = Relationship(back_populates="users")

    @property
    def gmail_connected(self) -> bool:
        return self.gmail_refresh_token_enc is not None