"""gmail refresh token + config email per lettertype

Revision ID: 32aafb646104
Revises: 5feedb3ddc44
Create Date: 2026-09-04 13:49:32.215554

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel memakai tipe kolomnya sendiri (mis. AutoString), yang muncul di
# berkas migrasi hasil autogenerate. Submodulnya diimpor eksplisit karena
# `import sqlmodel` saja tidak membuat sqlmodel.sql dikenali.
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '32aafb646104'
down_revision: Union[str, Sequence[str], None] = '5feedb3ddc44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fondasi Stage B (kirim surat via email).

    `user`:
    - `gmail_refresh_token_enc` — refresh token OAuth Gmail admin, sudah
      terenkripsi Fernet (app/core/crypto.py). NULL = admin belum menekan
      "Hubungkan Gmail". Nullable, tanpa backfill.
    - `gmail_connected_at` — kapan terakhir menghubungkan, untuk tampilan.

    `lettertype`:
    - `send_email_enabled` — semua jenis surat lama TIDAK mengirim email, jadi
      di-backfill False lewat server_default.
    - `email_subject_template` / `email_body_template` — NULL selama email
      belum dikonfigurasi; wajib terisi hanya saat send_email_enabled True
      (ditegakkan di layer API, bukan DB).

    Pakai op.add_column polos, BUKAN batch_alter_table: SQLite mendukung
    ADD COLUMN secara native, sedangkan batch mode membangun ulang tabel dan
    berisiko diam-diam menghilangkan UniqueConstraint uq_lettertype_unit_slug
    dan index unik user.email.
    """
    op.add_column(
        "user",
        sa.Column("gmail_refresh_token_enc", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "user",
        sa.Column("gmail_connected_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "lettertype",
        sa.Column("send_email_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "lettertype",
        sa.Column("email_subject_template", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )
    op.add_column(
        "lettertype",
        sa.Column("email_body_template", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lettertype", "email_body_template")
    op.drop_column("lettertype", "email_subject_template")
    op.drop_column("lettertype", "send_email_enabled")
    op.drop_column("user", "gmail_connected_at")
    op.drop_column("user", "gmail_refresh_token_enc")
