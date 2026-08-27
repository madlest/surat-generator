# Endpoint generate generik: bekerja untuk LetterType mana pun (bukan cuma
# SPM), berdasarkan LetterField yang tersimpan di database untuk slug terkait.

import json
import logging
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.job_store import job_store
from app.dependencies import get_current_user, scope_unit_id
from app.models.letter_type import LetterField
from app.models.organization import User
from app.services.document_generator import DocumentGenerationError
from app.services.dynamic_batch_generator import (
    DynamicBatchGenerationError,
    generate_batch,
    generate_preview,
)
from app.services.dynamic_fields import (
    FieldValidationError,
    parse_field_values,
    parse_recipients_from_csv,
    parse_recipients_from_list,
)
from app.services.letter_type_repo import (
    get_letter_type_by_unit_slug,
    split_fields_by_level,
)
from app.services.pdf_merger import PdfMergeError

router = APIRouter(prefix="/generate", tags=["Generate Surat Dinamis"])

logger = logging.getLogger(__name__)

# Job yang tidak pernah diunduh (gagal, atau tab user keburu ditutup) disapu
# setelah lewat umur ini, supaya entry-nya tidak menumpuk di memori.
JOB_MAX_AGE_SECONDS = 60 * 60  # 1 jam

MAX_LAMPIRAN_BYTES = 10 * 1024 * 1024  # 10 MB, sama dengan batas di frontend
PDF_MAGIC_BYTES = b"%PDF-"


def _save_lampiran(upload_file: UploadFile, dest_path: Path, position: int) -> None:
    """
    Simpan satu file lampiran ke disk sambil menegakkan batas ukuran dan
    memastikan isinya benar-benar PDF. Frontend sudah mengecek hal yang sama,
    tapi endpoint ini juga bisa dipanggil langsung (curl), jadi validasinya
    tidak boleh cuma mengandalkan sisi klien.
    """
    upload_file.file.seek(0)
    header = upload_file.file.read(len(PDF_MAGIC_BYTES))
    if header != PDF_MAGIC_BYTES:
        raise ValueError(f"Lampiran ke-{position} bukan file PDF yang valid.")

    total = len(header)
    with open(dest_path, "wb") as f:
        f.write(header)
        while chunk := upload_file.file.read(1024 * 1024):
            total += len(chunk)
            if total > MAX_LAMPIRAN_BYTES:
                f.close()
                dest_path.unlink(missing_ok=True)
                raise ValueError(f"Lampiran ke-{position} melebihi batas ukuran 10 MB.")
            f.write(chunk)


def _parse_base_info(raw: dict) -> dict:
    """
    Validasi & convert field universal yang berlaku untuk semua jenis surat
    (nomor_surat, tempat_surat, tanggal_surat, perihal_surat, lampirans).
    """
    # batch_info harus objek JSON, bukan array/angka/string. Tanpa guard ini
    # raw.get() melempar AttributeError dan berakhir jadi 500, padahal ini
    # murni kesalahan input.
    if not isinstance(raw, dict):
        raise FieldValidationError("Informasi surat", ["'batch_info' harus berupa objek JSON."])

    errors: list[str] = []

    for key, label in (
        ("nomor_surat", "Nomor Surat"),
        ("tempat_surat", "Tempat Surat"),
        ("perihal_surat", "Perihal"),
    ):
        if not str(raw.get(key, "")).strip():
            errors.append(f"'{label}' wajib diisi.")

    tanggal_surat = None
    tanggal_surat_raw = raw.get("tanggal_surat")
    if not tanggal_surat_raw:
        errors.append("'Tanggal Surat' wajib diisi.")
    else:
        try:
            # Nilai masuk selalu ISO (dikirim native date picker); pesan error
            # tetap memakai DD-MM-YYYY karena itu yang dilihat & diketik user.
            tanggal_surat = datetime.strptime(str(tanggal_surat_raw).strip(), "%Y-%m-%d").date()
        except ValueError:
            errors.append("'Tanggal Surat' harus berupa tanggal dengan format DD-MM-YYYY.")

    lampirans_raw = raw.get("lampirans", [])
    if not isinstance(lampirans_raw, list):
        raise FieldValidationError("Informasi surat", ["'lampirans' harus berupa list."])

    lampirans = []
    for index, item in enumerate(lampirans_raw, start=1):
        judul = str(item.get("judul", "")).strip() if isinstance(item, dict) else ""
        if not judul:
            errors.append(f"Judul lampiran ke-{index} wajib diisi.")
        lampirans.append({"judul": judul, "file_path": None})

    if errors:
        raise FieldValidationError("Informasi surat", errors)

    return {
        "nomor_surat": str(raw["nomor_surat"]).strip(),
        "tempat_surat": str(raw["tempat_surat"]).strip(),
        "tanggal_surat": tanggal_surat,
        "perihal_surat": str(raw["perihal_surat"]).strip(),
        "lampirans": lampirans,
    }


def _run_batch_job(
    job_id: str,
    template_path: str,
    base_info: dict,
    custom_batch_values: dict,
    batch_fields: list[LetterField],
    recipients: list[dict],
    recipient_fields: list[LetterField],
    working_dir: str,
):
    try:
        def on_progress(current: int, total: int):
            job_store.update_progress(job_id, current)

        zip_path = generate_batch(
            template_path=template_path,
            base_info=base_info,
            custom_batch_values=custom_batch_values,
            batch_fields=batch_fields,
            recipients=recipients,
            recipient_fields=recipient_fields,
            working_dir=working_dir,
            progress_callback=on_progress,
        )
        job_store.mark_done(job_id, zip_path)
    except (DocumentGenerationError, PdfMergeError, DynamicBatchGenerationError) as e:
        job_store.mark_error(job_id, str(e))
        shutil.rmtree(working_dir, ignore_errors=True)
    except Exception:
        logger.exception("Job generate %s gagal karena kesalahan tak terduga", job_id)
        job_store.mark_error(job_id, "Terjadi kesalahan tidak terduga saat memproses dokumen.")
        shutil.rmtree(working_dir, ignore_errors=True)


def _prepare_generate_request(
    unit_slug: str,
    slug: str,
    working_dir: Path,
    batch_info: str,
    recipients_mode: str,
    lampiran_files: list[UploadFile],
    recipients_json: str | None,
    recipients_csv: UploadFile | None,
    current_user: User,
):
    """
    Ambil LetterType untuk pasangan (unit_slug, slug), lalu urai & validasi
    batch_info, lampiran, dan recipients. Dipakai bersama oleh endpoint
    generate (job penuh) dan preview (satu penerima), supaya aturan
    validasinya tidak bercabang.

    Dicari lewat (unit_slug, slug), bukan slug saja — pasangan ini dijamin
    unik secara global oleh constraint database, jadi tidak ada ambiguitas
    "ambil yang pertama ketemu" seperti pada Stage 3a.

    Kepemilikan dicek SETELAH ditemukan (bukan lewat filter query) karena
    unit_slug sudah eksplisit di URL: kalau admin unit lain mengetik URL unit
    yang bukan miliknya, responsnya tetap 404 yang sama seperti benar-benar
    tidak ada — bukan 403 — supaya tidak bocor informasi jenis surat apa saja
    yang dipakai unit lain.

    working_dir harus sudah dibuat oleh pemanggil (butuh ada lebih dulu untuk
    tempat lampiran disimpan). Kalau terjadi error, folder ini dihapus di sini
    sebelum exception dilempar ke pemanggil.

    Mengembalikan (letter_type, batch_fields, recipient_fields, base_info,
    custom_batch_values, recipients).
    """
    with Session(engine) as session:
        result = get_letter_type_by_unit_slug(session, unit_slug, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")

    letter_type, fields = result

    unit_filter = scope_unit_id(current_user)
    if unit_filter is not None and letter_type.unit_id != unit_filter:
        raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")
    batch_fields, recipient_fields = split_fields_by_level(fields)

    try:
        try:
            batch_info_raw = json.loads(batch_info)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"batch_info bukan JSON valid: {e}")

        base_info = _parse_base_info(batch_info_raw)

        custom_fields_raw = batch_info_raw.get("custom_fields", {})
        if not isinstance(custom_fields_raw, dict):
            raise FieldValidationError("Informasi surat", ["'custom_fields' harus berupa objek JSON."])
        custom_batch_values = parse_field_values(custom_fields_raw, batch_fields, "Informasi surat")

        if len(lampiran_files) != len(base_info["lampirans"]):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Jumlah file lampiran ({len(lampiran_files)}) tidak sama dengan "
                    f"jumlah judul lampiran ({len(base_info['lampirans'])})."
                ),
            )

        lampiran_dir = working_dir / "lampiran"
        lampiran_dir.mkdir(parents=True, exist_ok=True)
        for index, upload_file in enumerate(lampiran_files):
            dest_path = lampiran_dir / f"lampiran_{index}.pdf"
            _save_lampiran(upload_file, dest_path, position=index + 1)
            base_info["lampirans"][index]["file_path"] = str(dest_path)

        if recipients_mode == "list":
            if not recipients_json:
                raise HTTPException(status_code=400, detail="recipients_json wajib diisi untuk mode 'list'.")
            try:
                recipients_data = json.loads(recipients_json)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"recipients_json bukan JSON valid: {e}")
            recipients = parse_recipients_from_list(recipients_data, recipient_fields)

        elif recipients_mode == "csv":
            if recipients_csv is None:
                raise HTTPException(status_code=400, detail="recipients_csv wajib diupload untuk mode 'csv'.")
            content = recipients_csv.file.read()
            recipients = parse_recipients_from_csv(content, recipient_fields)

        else:
            raise HTTPException(status_code=400, detail="recipients_mode harus 'list' atau 'csv'.")

    except FieldValidationError as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=e.errors)
    except ValueError as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(working_dir, ignore_errors=True)
        # Detail teknis (path, stack) hanya ke log server, bukan ke user.
        logger.exception("Gagal menyiapkan request generate untuk slug '%s'", slug)
        raise HTTPException(status_code=500, detail="Terjadi kesalahan tidak terduga di server.")

    return letter_type, batch_fields, recipient_fields, base_info, custom_batch_values, recipients


@router.post("/{unit_slug}/{slug}")
def start_generate_job(
    unit_slug: str,
    slug: str,
    background_tasks: BackgroundTasks,
    batch_info: str = Form(...),
    recipients_mode: str = Form(...),
    lampiran_files: list[UploadFile] | None = File(default=None),
    recipients_json: str | None = Form(default=None),
    recipients_csv: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
):
    job_id = uuid.uuid4().hex
    working_dir = Path(settings.temp_dir) / f"job_{job_id}"
    working_dir.mkdir(parents=True, exist_ok=True)

    letter_type, batch_fields, recipient_fields, base_info, custom_batch_values, recipients = (
        _prepare_generate_request(
            unit_slug,
            slug,
            working_dir,
            batch_info,
            recipients_mode,
            lampiran_files or [],
            recipients_json,
            recipients_csv,
            current_user,
        )
    )

    # Sapu job lama tiap kali ada job baru — cukup untuk skala pemakaian ini,
    # tanpa perlu scheduler terpisah.
    for stale_zip in job_store.sweep_stale(JOB_MAX_AGE_SECONDS):
        shutil.rmtree(Path(stale_zip).parent, ignore_errors=True)

    # Kepemilikan job disimpan sebagai unit LetterType-nya, bukan user yang
    # memicu — supaya sesama admin di unit yang sama tetap bisa saling
    # memantau job satu sama lain (konsisten dengan prinsip admin di-scope ke
    # unit, bukan ke akun pribadi).
    job_store.create_job(job_id=job_id, total=len(recipients), unit_id=letter_type.unit_id)
    background_tasks.add_task(
        _run_batch_job,
        job_id,
        letter_type.template_path,
        base_info,
        custom_batch_values,
        batch_fields,
        recipients,
        recipient_fields,
        str(working_dir),
    )

    return {"job_id": job_id, "total": len(recipients)}


@router.post("/{unit_slug}/{slug}/preview")
def preview_generate(
    unit_slug: str,
    slug: str,
    background_tasks: BackgroundTasks,
    batch_info: str = Form(...),
    recipients_mode: str = Form(...),
    lampiran_files: list[UploadFile] | None = File(default=None),
    recipients_json: str | None = Form(default=None),
    recipients_csv: UploadFile | None = File(default=None),
    current_user: User = Depends(get_current_user),
):
    """
    Generate satu dokumen (cover letter + lampiran tergabung) untuk penerima
    pertama saja, secara sinkron — dipakai frontend untuk pratinjau sebelum
    generate batch yang sesungguhnya. Tidak menyentuh job_store karena tidak
    ada progress untuk dipantau; folder kerja dibersihkan lewat
    background_tasks setelah PDF-nya terkirim ke klien, jadi tidak menumpuk
    seperti temp folder job biasa.
    """
    preview_id = uuid.uuid4().hex
    working_dir = Path(settings.temp_dir) / f"preview_{preview_id}"
    working_dir.mkdir(parents=True, exist_ok=True)

    letter_type, batch_fields, recipient_fields, base_info, custom_batch_values, recipients = (
        _prepare_generate_request(
            unit_slug,
            slug,
            working_dir,
            batch_info,
            recipients_mode,
            lampiran_files or [],
            recipients_json,
            recipients_csv,
            current_user,
        )
    )

    if not recipients:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail="Isi minimal satu penerima untuk membuat pratinjau.")

    try:
        pdf_path = generate_preview(
            template_path=letter_type.template_path,
            base_info=base_info,
            custom_batch_values=custom_batch_values,
            batch_fields=batch_fields,
            recipient_values=recipients[0],
            recipient_fields=recipient_fields,
            working_dir=str(working_dir),
        )
    except (DocumentGenerationError, PdfMergeError, DynamicBatchGenerationError) as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        shutil.rmtree(working_dir, ignore_errors=True)
        logger.exception("Gagal membuat pratinjau untuk slug '%s'", slug)
        raise HTTPException(status_code=500, detail="Terjadi kesalahan tidak terduga saat membuat pratinjau.")

    background_tasks.add_task(shutil.rmtree, working_dir, ignore_errors=True)

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename="pratinjau_surat.pdf",
        background=background_tasks,
    )


def _check_job_unit_access(job: dict, current_user: User) -> None:
    """
    Menolak akses ke job milik unit lain. Job disimpan dengan job_id acak
    (UUID), yang sudah cukup aman dari tebakan, tapi tetap ditegakkan di sini
    sebagai lapisan kedua — supaya kalau job_id tersebar (mis. ter-log atau
    ter-screenshot tanpa sengaja), admin unit lain tetap tidak bisa memantau
    atau mengunduh hasilnya. Superadmin (scope_unit_id -> None) selalu lolos.
    """
    unit_filter = scope_unit_id(current_user)
    if unit_filter is not None and job.get("unit_id") != unit_filter:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")


@router.get("/jobs/{job_id}/status")
def get_job_status(job_id: str, current_user: User = Depends(get_current_user)):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    _check_job_unit_access(job, current_user)
    return job


@router.get("/jobs/{job_id}/download")
def download_job_result(
    job_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    _check_job_unit_access(job, current_user)
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="Dokumen belum selesai diproses.")

    zip_path = job["zip_path"]
    working_dir = Path(zip_path).parent

    background_tasks.add_task(shutil.rmtree, working_dir, ignore_errors=True)
    background_tasks.add_task(job_store.delete, job_id)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename="hasil_surat.zip",
        background=background_tasks,
    )