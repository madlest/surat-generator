"""pindahkan template ke folder per-unit

Revision ID: 5b9ba1f55c1a
Revises: a1f4c9e27b30
Create Date: 2026-08-27 15:02:11.884113

"""
from pathlib import Path
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b9ba1f55c1a'
down_revision: Union[str, Sequence[str], None] = 'a1f4c9e27b30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Path dasar folder upload. Ditulis literal (bukan diimpor dari app.routers.admin)
# supaya migrasi ini tetap stabil dan bisa dijalankan persis sama walau kode
# aplikasi di masa depan merefaktor konstanta itu.
UPLOAD_DIR = Path("app/templates/uploaded")


def upgrade() -> None:
    """
    Pindahkan tiap file template dari `{slug}.docx` (flat, dipakai bersama
    lintas unit) ke `{unit_slug}/{slug}.docx` (terpisah per unit), lalu
    perbarui kolom template_path supaya kode aplikasi (yang sejak Stage 3b
    membaca dari lokasi baru ini) tetap menemukan filenya.

    Mencakup baris yang sudah diarsipkan juga (deleted_at IS NOT NULL) —
    template-nya tetap harus ikut pindah supaya fitur pulihkan-dari-arsip
    tidak menunjuk ke file yang sudah tidak ada di lokasi lama.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT lt.id, lt.slug, lt.template_path, u.slug AS unit_slug "
            "FROM lettertype lt JOIN unit u ON u.id = lt.unit_id"
        )
    ).fetchall()

    for row in rows:
        old_path = Path(row.template_path)
        unit_dir = UPLOAD_DIR / row.unit_slug
        new_path = unit_dir / f"{row.slug}.docx"

        if old_path.exists():
            unit_dir.mkdir(parents=True, exist_ok=True)
            # Kalau kebetulan file tujuan sudah ada (mis. migrasi ini
            # terulang setelah gagal di tengah jalan), jangan menimpa diam-
            # diam — but this only happens if old_path itself still exists,
            # yang berarti percobaan sebelumnya belum sempat rename. Aman.
            old_path.rename(new_path)
        else:
            # File sumbernya sendiri sudah tidak ada di disk (kemungkinan
            # sudah pernah dipindah manual, atau memang hilang). Tetap catat
            # lokasi barunya di database supaya konsisten dengan skema baru;
            # operator perlu menaruh file itu manual kalau memang masih
            # dibutuhkan.
            print(
                f"[migrasi] PERINGATAN: file template tidak ditemukan di "
                f"{old_path} untuk LetterType id={row.id} (slug={row.slug!r}). "
                f"template_path tetap diperbarui ke lokasi baru, tapi file "
                f"perlu ditaruh manual kalau memang masih diperlukan."
            )

        conn.execute(
            sa.text("UPDATE lettertype SET template_path = :new_path WHERE id = :id"),
            {"new_path": new_path.as_posix(), "id": row.id},
        )


def downgrade() -> None:
    """
    Kembalikan file ke skema flat lama. Ditolak (dengan error jelas) kalau
    ada dua unit yang sekarang memakai slug sama — turun versi di keadaan itu
    berarti salah satu file akan menimpa yang lain, sengaja dihentikan
    daripada diam-diam kehilangan data.
    """
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT lt.id, lt.slug, lt.template_path, u.slug AS unit_slug "
            "FROM lettertype lt JOIN unit u ON u.id = lt.unit_id"
        )
    ).fetchall()

    slug_counts: dict[str, int] = {}
    for row in rows:
        slug_counts[row.slug] = slug_counts.get(row.slug, 0) + 1
    bentrok = [slug for slug, count in slug_counts.items() if count > 1]
    if bentrok:
        raise RuntimeError(
            f"Tidak bisa turun versi: slug {bentrok!r} dipakai lebih dari satu unit. "
            "Turun ke skema flat lama akan membuat file-file itu saling menimpa. "
            "Ganti salah satu slug yang bentrok dulu sebelum downgrade."
        )

    for row in rows:
        old_path = Path(row.template_path)  # lokasi baru: {unit_slug}/{slug}.docx
        new_path = UPLOAD_DIR / f"{row.slug}.docx"  # lokasi lama: flat

        if old_path.exists():
            old_path.rename(new_path)
        else:
            print(
                f"[migrasi] PERINGATAN: file template tidak ditemukan di "
                f"{old_path} untuk LetterType id={row.id} (slug={row.slug!r}) saat downgrade."
            )

        conn.execute(
            sa.text("UPDATE lettertype SET template_path = :new_path WHERE id = :id"),
            {"new_path": new_path.as_posix(), "id": row.id},
        )
