# Helper query untuk mengambil LetterType beserta field-fieldnya by slug.

from sqlmodel import Session, select

from app.models.letter_type import FieldLevel, LetterField, LetterType


def get_letter_type_with_fields(session: Session, slug: str) -> tuple[LetterType, list[LetterField]] | None:
    letter_type = session.exec(select(LetterType).where(LetterType.slug == slug)).first()
    if not letter_type:
        return None

    fields = session.exec(
        select(LetterField)
        .where(LetterField.letter_type_id == letter_type.id)
        .order_by(LetterField.display_order)
    ).all()

    return letter_type, list(fields)


def split_fields_by_level(fields: list[LetterField]) -> tuple[list[LetterField], list[LetterField]]:
    """Mengembalikan (batch_fields, recipient_fields)."""
    batch_fields = [f for f in fields if f.level == FieldLevel.batch]
    recipient_fields = [f for f in fields if f.level == FieldLevel.recipient]
    return batch_fields, recipient_fields
