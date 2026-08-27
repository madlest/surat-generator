import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session, col, select

from app.core.database import engine
from app.models.letter_type import FieldLevel, FieldType, LetterType, LetterField
from app.services.letter_type_repo import get_letter_type_with_fields
from app.services.template_inspector import TemplateInspectionError, detect_custom_variables

router = APIRouter(prefix="/admin/letter-types", tags=["Admin - Jenis Surat"])

UPLOAD_DIR = Path("app/templates/uploaded")

# Slug dipakai langsung sebagai nama file template, jadi bentuknya dibatasi
# ketat: huruf kecil, angka, dan tanda hubung. Tanpa ini, slug seperti
# "../../etc/passwd" bisa menulis file di luar folder yang dimaksud.
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_SLUG_LENGTH = 60


def _validate_identity(raw_name: str, raw_slug: str) -> tuple[str, str]:
    """Bersihkan dan validasi nama serta slug jenis surat."""
    cleaned_name = raw_name.strip()
    cleaned_slug = raw_slug.strip().lower()

    if not cleaned_name:
        raise HTTPException(status_code=400, detail="Nama jenis surat wajib diisi.")
    if len(cleaned_slug) > MAX_SLUG_LENGTH or not SLUG_PATTERN.match(cleaned_slug):
        raise HTTPException(
            status_code=400,
            detail=(
                "Slug hanya boleh berisi huruf kecil, angka, dan tanda hubung "
                f"(maksimal {MAX_SLUG_LENGTH} karakter). Contoh: permohonan-mengajar."
            ),
        )
    return cleaned_name, cleaned_slug


def _normalize_fields_config(fields_config: str) -> list[dict]:
    """
    Urai dan validasi definisi field dari klien menjadi bentuk baku yang siap
    dipakai membuat LetterField. Dipakai bersama oleh endpoint create dan
    update supaya aturan validasinya tidak bercabang lalu lambat laun berbeda.
    """
    try:
        fields_data = json.loads(fields_config)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"fields_config bukan JSON valid: {e}")

    if not isinstance(fields_data, list):
        raise HTTPException(status_code=400, detail="fields_config harus berupa list.")

    valid_types = {t.value for t in FieldType}
    valid_levels = {level.value for level in FieldLevel}
    seen_keys: set[str] = set()
    normalized: list[dict] = []

    for position, field_data in enumerate(fields_data, start=1):
        if not isinstance(field_data, dict):
            raise HTTPException(status_code=400, detail=f"Definisi field ke-{position} harus berupa objek.")

        field_key = str(field_data.get("field_key", "")).strip()
        if not field_key:
            raise HTTPException(status_code=400, detail=f"Definisi field ke-{position} tidak punya field_key.")
        if field_key in seen_keys:
            raise HTTPException(status_code=400, detail=f"field_key '{field_key}' muncul lebih dari sekali.")
        seen_keys.add(field_key)

        field_type = str(field_data.get("field_type", "text"))
        if field_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Tipe '{field_type}' pada field '{field_key}' tidak dikenal.",
            )

        level = str(field_data.get("level", ""))
        if level not in valid_levels:
            raise HTTPException(
                status_code=400,
                detail=f"Level '{level}' pada field '{field_key}' tidak dikenal.",
            )

        normalized.append(
            {
                "field_key": field_key,
                "label": str(field_data.get("label", "")).strip() or field_key,
                "field_type": field_type,
                "level": level,
                # Tanggal di surat resmi tidak boleh kosong: paksa wajib apa pun
                # yang dikirim klien, supaya tidak bisa di-bypass lewat curl.
                "required": True if field_type == FieldType.date else bool(field_data.get("required", True)),
            }
        )

    return normalized


def _save_template(template_file: UploadFile, dest_path: Path) -> None:
    """
    Simpan template docx ke lokasi tujuan, lalu pastikan isinya benar-benar
    bisa dibaca docxtpl. File yang rusak dibuang lagi supaya tidak tertinggal.
    """
    with open(dest_path, "wb") as f:
        shutil.copyfileobj(template_file.file, f)
    try:
        detect_custom_variables(str(dest_path))
    except TemplateInspectionError as e:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(e))


def _replace_fields(session: Session, letter_type_id: int, normalized_fields: list[dict]) -> None:
    """Ganti seluruh LetterField milik satu jenis surat dengan definisi baru."""
    for field in session.exec(
        select(LetterField).where(LetterField.letter_type_id == letter_type_id)
    ).all():
        session.delete(field)
    session.flush()

    for index, field_data in enumerate(normalized_fields):
        session.add(LetterField(letter_type_id=letter_type_id, display_order=index, **field_data))


@router.post("/inspect")
def inspect_template(template_file: UploadFile = File(...)):
    """
    Langkah 1: upload docx untuk dideteksi variabel custom-nya,
    TANPA menyimpan apa pun secara permanen. Admin melihat hasil
    deteksi ini dulu sebelum submit konfigurasi lengkap di langkah 2.
    """
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Nama file dibuat acak, bukan diambil dari template_file.filename, karena
    # nama kiriman klien bisa mengandung "../" atau kebetulan sama dengan
    # template permanen di folder ini - yang berarti file preview sementara
    # menimpanya, lalu ikut terhapus di blok finally.
    temp_path = UPLOAD_DIR / f"_preview_{uuid.uuid4().hex}.docx"

    try:
        with open(temp_path, "wb") as f:
            shutil.copyfileobj(template_file.file, f)
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
    name, slug = _validate_identity(name, slug)
    normalized_fields = _normalize_fields_config(fields_config)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    final_path = UPLOAD_DIR / f"{slug}.docx"

    with Session(engine) as session:
        # Jenis surat yang diarsipkan tetap memegang slug-nya. Tanpa pesan yang
        # membedakan, admin akan bingung: slug ditolak padahal tidak ada kartu
        # dengan nama itu di dashboard.
        existing = session.exec(select(LetterType).where(LetterType.slug == slug)).first()
        if existing and existing.deleted_at is not None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Slug '{slug}' dipakai jenis surat yang ada di arsip. "
                    "Pulihkan atau hapus permanen dulu lewat halaman arsip."
                ),
            )
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug '{slug}' sudah terdaftar di database.")
        if final_path.exists():
            raise HTTPException(status_code=400, detail=f"Slug '{slug}' sudah digunakan.")

        # Semua validasi lolos - baru sekarang aman menulis file ke disk.
        _save_template(template_file, final_path)

        try:
            # as_posix() (bukan str()) supaya path selalu tersimpan dengan forward
            # slash. str() mengikuti OS yang sedang jalan, sehingga data yang dibuat
            # di Windows tidak terbaca saat aplikasi dijalankan di Linux.
            letter_type = LetterType(name=name, slug=slug, template_path=final_path.as_posix())
            session.add(letter_type)
            session.commit()
            session.refresh(letter_type)

            if letter_type.id is None:
                raise HTTPException(status_code=500, detail="Gagal membuat jenis surat.")

            _replace_fields(session, letter_type.id, normalized_fields)
            session.commit()

            # Disalin selagi session masih hidup: setelah commit, SQLAlchemy
            # meng-expire atribut objek, sehingga akses di luar blok `with`
            # akan melempar DetachedInstanceError.
            result = {"id": letter_type.id, "slug": letter_type.slug, "name": letter_type.name}
        except Exception:
            # Jangan tinggalkan file template yatim kalau penyimpanan gagal.
            session.rollback()
            final_path.unlink(missing_ok=True)
            raise

    return result


@router.put("/{slug}")
def update_letter_type(
    slug: str,
    name: str = Form(...),
    new_slug: str = Form(...),
    fields_config: str = Form(...),
    template_file: UploadFile | None = File(default=None),
):
    """
    Perbarui jenis surat yang sudah ada: nama, slug, konfigurasi field, dan
    (opsional) template docx-nya. Tanpa endpoint ini, satu-satunya cara
    memperbaiki salah konfigurasi adalah menyunting SQLite secara langsung.

    Konfigurasi field dikirim utuh, bukan sebagai tambalan sebagian: server
    mengganti seluruh LetterField milik jenis surat ini dengan kiriman klien.
    Jauh lebih mudah diprediksi daripada menyelisihkan perubahan satu per satu,
    dan wizard di frontend memang selalu mengirim keadaan lengkap.

    Catatan soal ganti slug: slug menentukan nama file template sekaligus URL
    /generate/{slug}, jadi mengubahnya memindahkan file di disk dan memutus
    tautan lama ke jenis surat ini.
    """
    name, new_slug = _validate_identity(name, new_slug)
    normalized_fields = _normalize_fields_config(fields_config)

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    # Simpan berkasnya sendiri, bukan sekadar penanda boolean: penyempitan tipe
    # tidak menular lewat variabel perantara, sehingga _save_template tetap
    # menerima UploadFile yang pasti bukan None.
    template_baru: UploadFile | None = (
        template_file if template_file is not None and template_file.filename else None
    )

    with Session(engine) as session:
        letter_type = session.exec(
            select(LetterType)
            .where(LetterType.slug == slug)
            .where(col(LetterType.deleted_at).is_(None))
        ).first()
        if not letter_type:
            raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")
        if letter_type.id is None:
            raise HTTPException(status_code=500, detail="Jenis surat tidak punya id.")

        old_path = Path(letter_type.template_path)
        new_path = UPLOAD_DIR / f"{new_slug}.docx"
        slug_berubah = new_slug != slug

        if slug_berubah:
            bentrok = session.exec(select(LetterType).where(LetterType.slug == new_slug)).first()
            if bentrok:
                di_arsip = " yang ada di arsip" if bentrok.deleted_at is not None else " lain"
                raise HTTPException(
                    status_code=400,
                    detail=f"Slug '{new_slug}' sudah dipakai jenis surat{di_arsip}.",
                )
            if new_path.exists():
                raise HTTPException(
                    status_code=400,
                    detail=f"Sudah ada file template bernama '{new_slug}.docx'.",
                )
        if slug_berubah and template_baru is None and not old_path.exists():
            raise HTTPException(
                status_code=400,
                detail="File template lama tidak ditemukan, unggah ulang template saat mengganti slug.",
            )

        # Salin template lama sebelum disentuh, supaya keadaan bisa dikembalikan
        # utuh kalau ada langkah berikutnya yang gagal.
        if old_path.exists():
            backup_path = UPLOAD_DIR / f"_backup_{uuid.uuid4().hex}.docx"
            shutil.copy2(old_path, backup_path)

        try:
            if template_baru is not None:
                _save_template(template_baru, new_path)
                if slug_berubah:
                    old_path.unlink(missing_ok=True)
            elif slug_berubah:
                old_path.rename(new_path)

            letter_type.name = name
            letter_type.slug = new_slug
            letter_type.template_path = new_path.as_posix()
            session.add(letter_type)

            _replace_fields(session, letter_type.id, normalized_fields)
            session.commit()
            session.refresh(letter_type)

            result = {"id": letter_type.id, "slug": letter_type.slug, "name": letter_type.name}
        except Exception:
            session.rollback()
            # Pulihkan keadaan file: buang hasil tulisan baru, lalu kembalikan
            # salinan cadangan ke lokasi asalnya.
            if slug_berubah or template_baru is not None:
                new_path.unlink(missing_ok=True)
            if backup_path and backup_path.exists():
                shutil.copy2(backup_path, old_path)
            raise
        finally:
            if backup_path:
                backup_path.unlink(missing_ok=True)

    return result


@router.delete("/{slug}")
def archive_letter_type(slug: str, confirm_name: str):
    """
    Arsipkan jenis surat: barisnya ditandai terhapus, bukan dibuang.

    Seluruh LetterField dan berkas templatnya sengaja dibiarkan utuh supaya
    pemulihan mengembalikan keadaan persis seperti semula. Membuang barisnya
    berarti konfigurasi field ikut hilang, dan "pulihkan" cuma akan berarti
    "unggah ulang lalu atur dari nol".

    Nama jenis surat harus diketik ulang persis sebagai konfirmasi. Syarat ini
    ditegakkan di server juga, bukan hanya di UI, karena endpoint ini bisa
    dipanggil langsung.
    """
    with Session(engine) as session:
        letter_type = session.exec(
            select(LetterType)
            .where(LetterType.slug == slug)
            .where(col(LetterType.deleted_at).is_(None))
        ).first()
        if not letter_type:
            raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")

        if confirm_name.strip() != letter_type.name:
            raise HTTPException(
                status_code=400,
                detail="Nama konfirmasi tidak cocok dengan nama jenis surat.",
            )

        letter_type.deleted_at = datetime.now()
        session.add(letter_type)
        session.commit()

    return {"slug": slug, "archived": True}


@router.post("/archived/{slug}/restore")
def restore_letter_type(slug: str):
    """
    Kembalikan jenis surat dari arsip, lengkap dengan seluruh konfigurasi
    field-nya. Templatnya tidak pernah dipindah, jadi tidak ada yang perlu
    disusun ulang.
    """
    with Session(engine) as session:
        letter_type = session.exec(
            select(LetterType)
            .where(LetterType.slug == slug)
            .where(col(LetterType.deleted_at).is_not(None))
        ).first()
        if not letter_type:
            raise HTTPException(status_code=404, detail="Jenis surat tidak ada di arsip.")

        letter_type.deleted_at = None
        session.add(letter_type)
        session.commit()
        session.refresh(letter_type)
        result = {"id": letter_type.id, "slug": letter_type.slug, "name": letter_type.name}

    return result


@router.delete("/archived/{slug}/purge")
def purge_letter_type(slug: str, confirm_name: str):
    """
    Hapus jenis surat dari arsip untuk selamanya: barisnya, seluruh
    LetterField-nya, dan berkas templatnya. Tidak ada jalan kembali setelah ini.
    """
    with Session(engine) as session:
        letter_type = session.exec(
            select(LetterType)
            .where(LetterType.slug == slug)
            .where(col(LetterType.deleted_at).is_not(None))
        ).first()
        if not letter_type:
            raise HTTPException(status_code=404, detail="Jenis surat tidak ada di arsip.")

        if confirm_name.strip() != letter_type.name:
            raise HTTPException(
                status_code=400,
                detail="Nama konfirmasi tidak cocok dengan nama jenis surat.",
            )

        template_path = Path(letter_type.template_path)

        for field in session.exec(
            select(LetterField).where(LetterField.letter_type_id == letter_type.id)
        ).all():
            session.delete(field)

        session.delete(letter_type)
        session.commit()

    # Berkas dibuang setelah database berhasil diperbarui. Kalau urutannya
    # dibalik dan commit gagal, templatnya sudah lenyap sementara barisnya
    # masih ada — jenis surat yang tidak mungkin dipakai maupun dipulihkan.
    template_path.unlink(missing_ok=True)

    return {"slug": slug, "purged": True}


@router.get("")
def list_letter_types():
    """Daftar jenis surat yang aktif. Yang diarsipkan tidak ikut."""
    with Session(engine) as session:
        return session.exec(
            select(LetterType).where(col(LetterType.deleted_at).is_(None))
        ).all()


@router.get("/archived")
def list_archived_letter_types():
    """
    Daftar jenis surat yang sudah diarsipkan, terbaru lebih dulu.

    Rute ini harus didaftarkan sebelum GET "/{slug}", kalau tidak "archived"
    akan tertangkap sebagai slug.
    """
    with Session(engine) as session:
        return session.exec(
            select(LetterType)
            .where(col(LetterType.deleted_at).is_not(None))
            .order_by(col(LetterType.deleted_at).desc())
        ).all()


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


@router.get("/{slug}/template")
def download_current_template(slug: str):
    """
    Unduh file template .docx yang sedang aktif untuk satu jenis surat —
    supaya admin punya salinan yang persis dipakai sistem saat ini sebagai
    acuan/basis kalau mau merevisi (mis. nambah placeholder baru tanpa
    kehilangan format asli yang sudah ada).
    """
    with Session(engine) as session:
        letter_type = session.exec(
            select(LetterType).where(LetterType.slug == slug, col(LetterType.deleted_at).is_(None))
        ).first()
    if not letter_type:
        raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")

    template_path = Path(letter_type.template_path)
    if not template_path.exists():
        # Semestinya tidak pernah terjadi selama app/templates/uploaded/ tidak
        # diutak-atik manual di luar aplikasi, tapi dicek eksplisit supaya
        # errornya jelas ketimbang FileResponse gagal diam-diam.
        raise HTTPException(
            status_code=404,
            detail="Berkas template tidak ditemukan di server. Hubungi pengembang.",
        )

    # Nama unduhan pakai nama jenis surat (bukan slug/nama file internal),
    # supaya langsung jelas isinya apa saat admin buka folder unduhan.
    download_filename = f"template_{slug}.docx"
    return FileResponse(
        path=template_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_filename,
    )