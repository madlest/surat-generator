# Helper query untuk mengambil LetterType beserta field-fieldnya by slug.

from sqlmodel import Session, col, select

from app.models.letter_type import FieldLevel, LetterField, LetterType


def get_letter_type_with_fields(
    session: Session, slug: str, include_deleted: bool = False
) -> tuple[LetterType, list[LetterField]] | None:
    """
    Ambil jenis surat beserta field-fieldnya.

    Jenis surat yang sudah diarsipkan disembunyikan secara bawaan — ini juga
    yang membuat /generate/{slug} otomatis menolaknya, tanpa perlu pengecekan
    terpisah di sana. Halaman arsip memakai include_deleted=True.
    """
    query = select(LetterType).where(LetterType.slug == slug)
    if not include_deleted:
        query = query.where(col(LetterType.deleted_at).is_(None))

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