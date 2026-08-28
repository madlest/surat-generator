"""field manual dan tipe kontak email/phone

Revision ID: 5feedb3ddc44
Revises: 5b9ba1f55c1a
Create Date: 2026-08-28 15:15:24.658974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# SQLModel memakai tipe kolomnya sendiri (mis. AutoString), yang muncul di
# berkas migrasi hasil autogenerate. Submodulnya diimpor eksplisit karena
# `import sqlmodel` saja tidak membuat sqlmodel.sql dikenali.
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = '5feedb3ddc44'
down_revision: Union[str, Sequence[str], None] = '5b9ba1f55c1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Dua kolom baru di `letterfield`:

    - `from_template` — semua field yang ada sekarang berasal dari scan template,
      jadi di-backfill True lewat server_default. Field manual (from_template
      False) baru muncul setelah fitur ini dipakai.
    - `filled_by` — semua 'admin' untuk sekarang; kolom disiapkan untuk portal
      mahasiswa. server_default membuat baris lama valid tanpa UPDATE terpisah.

    Tipe kolom `field_type` tidak berubah (tetap string tanpa CHECK constraint —
    nilai email/phone divalidasi di layer Pydantic), jadi tidak ada perubahan
    skema untuk itu.
    """
    op.add_column(
        "letterfield",
        sa.Column("from_template", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "letterfield",
        sa.Column(
            "filled_by",
            sqlmodel.sql.sqltypes.AutoString(),
            nullable=False,
            server_default="admin",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("letterfield", "filled_by")
    op.drop_column("letterfield", "from_template")
