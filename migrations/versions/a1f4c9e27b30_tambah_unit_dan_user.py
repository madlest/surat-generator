"""tambah unit dan user

Revision ID: a1f4c9e27b30
Revises: 3433c3739100
Create Date: 2026-08-27 10:41:18.204773

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'a1f4c9e27b30'
down_revision: Union[str, Sequence[str], None] = '3433c3739100'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Semua jenis surat yang sudah ada dibuat sebelum konsep unit ada, dan semuanya
# milik Farmasi. Unit ini dibuat di dalam migrasi supaya database produksi tidak
# pernah melewati keadaan di mana unit_id kosong.
DEFAULT_UNIT_SLUG = "farmasi"
DEFAULT_UNIT_NAME = "Fakultas Farmasi"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'unit',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_unit_slug'), 'unit', ['slug'], unique=True)

    op.create_table(
        'user',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('picture_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
        sa.Column('role', sa.Enum('superadmin', 'admin', name='userrole'), nullable=False),
        sa.Column('unit_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['unit_id'], ['unit.id'], name='fk_user_unit_id_unit'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_email'), 'user', ['email'], unique=True)
    op.create_index(op.f('ix_user_unit_id'), 'user', ['unit_id'], unique=False)

    # Baris unit bawaan harus ada lebih dulu, karena backfill di bawah menunjuk
    # ke id-nya.
    unit_id = op.get_bind().execute(
        sa.text(
            "INSERT INTO unit (slug, name, created_at) "
            "VALUES (:slug, :name, CURRENT_TIMESTAMP) RETURNING id"
        ),
        {"slug": DEFAULT_UNIT_SLUG, "name": DEFAULT_UNIT_NAME},
    ).scalar_one()

    # Ditambahkan nullable dulu supaya baris lama tidak ditolak, baru diisi,
    # baru dikencangkan jadi NOT NULL. Menambah kolom NOT NULL tanpa default ke
    # tabel berisi data akan gagal.
    op.add_column('lettertype', sa.Column('unit_id', sa.Integer(), nullable=True))
    op.execute(
        sa.text("UPDATE lettertype SET unit_id = :uid").bindparams(uid=unit_id)
    )

    # Indeks unik lama pada slug dilepas di luar batch. Kalau dibiarkan, batch
    # akan menyalinnya apa adanya ke tabel baru dan keunikan global tetap
    # berlaku — persis yang ingin dihilangkan.
    op.drop_index(op.f('ix_lettertype_slug'), table_name='lettertype')

    with op.batch_alter_table('lettertype', schema=None) as batch_op:
        batch_op.alter_column('unit_id', existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            'fk_lettertype_unit_id_unit', 'unit', ['unit_id'], ['id']
        )
        batch_op.create_unique_constraint('uq_lettertype_unit_slug', ['unit_id', 'slug'])

    # Slug tetap diindeks untuk pencarian, tapi tanpa unique.
    op.create_index(op.f('ix_lettertype_slug'), 'lettertype', ['slug'], unique=False)
    op.create_index(op.f('ix_lettertype_unit_id'), 'lettertype', ['unit_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_lettertype_unit_id'), table_name='lettertype')
    op.drop_index(op.f('ix_lettertype_slug'), table_name='lettertype')

    with op.batch_alter_table('lettertype', schema=None) as batch_op:
        batch_op.drop_constraint('uq_lettertype_unit_slug', type_='unique')
        batch_op.drop_constraint('fk_lettertype_unit_id_unit', type_='foreignkey')
        batch_op.drop_column('unit_id')

    # Keunikan global dipulihkan. Ini bisa gagal kalau sudah ada dua unit yang
    # memakai slug sama — memang disengaja: turun versi dalam keadaan itu akan
    # menghilangkan data, jadi lebih baik berhenti dengan galat yang jelas.
    op.create_index(op.f('ix_lettertype_slug'), 'lettertype', ['slug'], unique=True)

    op.drop_index(op.f('ix_user_unit_id'), table_name='user')
    op.drop_index(op.f('ix_user_email'), table_name='user')
    op.drop_table('user')
    op.drop_index(op.f('ix_unit_slug'), table_name='unit')
    op.drop_table('unit')
