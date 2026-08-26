import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.database import engine
from app.models.letter_type import LetterType, LetterField
from app.services.letter_type_repo import get_letter_type_with_fields
from app.services.template_inspector import TemplateInspectionError, detect_custom_variables

router = APIRouter(prefix="/admin/letter-types", tags=["Admin - Jenis Surat"])

UPLOAD_DIR = Path("app/templates/uploaded")


@router.post("/inspect")
def inspect_template(template_file: UploadFile = File(...)):
    """
    Langkah 1: upload docx untuk dideteksi variabel custom-nya,
    TANPA menyimpan apa pun secara permanen. Admin melihat hasil
    deteksi ini dulu sebelum submit konfigurasi lengkap di langkah 2.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temp_path = UPLOAD_DIR / f"_preview_{template_file.filename}"

    with open(temp_path, "wb") as f:
        shutil.copyfileobj(template_file.file, f)

    try:
        variables = detect_custom_variables(str(temp_path))
    except TemplateInspectionError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        temp_path.unlink(missing_ok=True)

    return {"detected_variables": variables}


@router.post("")
def create_letter_type(
    name: str = Form(...),
    slug: str = Form(...),
    fields_config: str = Form(...),  # JSON string: list of {field_key, label, field_type, level, required}
    template_file: UploadFile = File(...),
):
    """
    Langkah 2: submit definisi lengkap jenis surat baru, termasuk
    template docx final (disimpan permanen kali ini) dan konfigurasi
    tiap field yang sudah diisi admin berdasarkan hasil /inspect.
    """
    try:
        fields_data = json.loads(fields_config)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"fields_config bukan JSON valid: {e}")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    final_path = UPLOAD_DIR / f"{slug}.docx"

    if final_path.exists():
        raise HTTPException(status_code=400, detail=f"Slug '{slug}' sudah digunakan.")

    with open(final_path, "wb") as f:
        shutil.copyfileobj(template_file.file, f)

    with Session(engine) as session:
        existing = session.exec(select(LetterType).where(LetterType.slug == slug)).first()
        if existing:
            final_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Slug '{slug}' sudah terdaftar di database.")

        letter_type = LetterType(name=name, slug=slug, template_path=final_path.as_posix())
        session.add(letter_type)
        session.commit()
        session.refresh(letter_type)

        if letter_type.id is None:
            raise HTTPException(status_code=500, detail="Gagal membuat jenis surat.")

        for index, field_data in enumerate(fields_data):
            field = LetterField(
                letter_type_id=letter_type.id,
                field_key=field_data["field_key"],
                label=field_data["label"],
                field_type=field_data.get("field_type", "text"),
                level=field_data["level"],
                required=field_data.get("required", True),
                display_order=index,
            )
            session.add(field)

        session.commit()
        result = {"id": letter_type.id, "slug": letter_type.slug, "name": letter_type.name}

    return result


@router.get("")
def list_letter_types():
    with Session(engine) as session:
        letter_types = session.exec(select(LetterType)).all()
        return letter_types


@router.get("/{slug}")
def get_letter_type(slug: str):
    with Session(engine) as session:
        result = get_letter_type_with_fields(session, slug)
        if not result:
            raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")

        letter_type, fields = result
        return {
            "id": letter_type.id,
            "slug": letter_type.slug,
            "name": letter_type.name,
            "fields": fields,
        }