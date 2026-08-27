# Helper query untuk mengambil LetterType beserta field-fieldnya by slug.

from sqlmodel import Session, col, select

from app.models.letter_type import FieldLevel, LetterField, LetterType


def get_letter_type_with_fields(
    session: Session, slug: str, include_deleted: bool = False, unit_id: int | None = None
) -> tuple[LetterType, list[LetterField]] | None:
    """
    Ambil jenis surat beserta field-fieldnya.

    Jenis surat yang sudah diarsipkan disembunyikan secara bawaan — ini juga
    yang membuat /generate/{slug} otomatis menolaknya, tanpa perlu pengecekan
    terpisah di sana. Halaman arsip memakai include_deleted=True.

    unit_id, kalau diisi, membatasi pencarian ke jenis surat milik unit itu
    saja — dipakai untuk admin biasa (di-scope ke unitnya). Superadmin
    memanggil dengan unit_id=None untuk mencari lintas semua unit.

    Sengaja mengembalikan None (bukan raise 403) kalau slug ada tapi di unit
    lain: dari sudut pandang admin yang tidak berhak, jenis surat milik unit
    lain harus terlihat identik dengan yang benar-benar tidak ada, supaya
    tidak bocor informasi slug apa saja yang dipakai unit lain.
    """
    query = select(LetterType).where(LetterType.slug == slug)
    if not include_deleted:
        query = query.where(col(LetterType.deleted_at).is_(None))
    if unit_id is not None:
        query = query.where(LetterType.unit_id == unit_id)

    letter_type = session.exec(query).first()
    if not letter_type:
        return None

    fields = session.exec(
        select(LetterField)
        .where(LetterField.letter_type_id == letter_type.id)
        # col() dipakai karena type checker melihat display_order sebagai int
        # (anotasi atribut instans), bukan sebagai kolom yang bisa diurutkan.
        .order_by(col(LetterField.display_order))
    ).all()

    return letter_type, list(fields)


def split_fields_by_level(fields: list[LetterField]) -> tuple[list[LetterField], list[LetterField]]:
    """Mengembalikan (batch_fields, recipient_fields)."""
    batch_fields = [f for f in fields if f.level == FieldLevel.batch]
    recipient_fields = [f for f in fields if f.level == FieldLevel.recipient]
    return batch_fields, recipient_fields