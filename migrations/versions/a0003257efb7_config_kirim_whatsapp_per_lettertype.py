"""config kirim whatsapp per lettertype

Revision ID: a0003257efb7
Revises: 92dac5e70cd0
Create Date: 2026-09-06 18:15:18.256137

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision: str = 'a0003257efb7'
down_revision: Union[str, Sequence[str], None] = '92dac5e70cd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Stage C — notifikasi WhatsApp per jenis surat. Sejalan dengan
    `send_email_enabled` dkk dari migrasi `32aafb646104`.

    `add_column` polos (bukan batch): SQLite dukung ADD COLUMN native, batch
    membangun ulang tabel dan berisiko menghilangkan UniqueConstraint
    `uq_lettertype_unit_slug`.
    """
    op.add_column(
        "lettertype",
        sa.Column("send_whatsapp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "lettertype",
        sa.Column("whatsapp_message_template", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lettertype", "whatsapp_message_template")
    op.drop_column("lettertype", "send_whatsapp_enabled")
