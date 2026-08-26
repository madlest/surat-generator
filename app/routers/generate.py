# Endpoint generate generik: bekerja untuk LetterType mana pun (bukan cuma
# SPM), berdasarkan LetterField yang tersimpan di database untuk slug terkait.

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine
from app.core.job_store import job_store
from app.models.letter_type import LetterField
from app.services.document_generator import DocumentGenerationError
from app.services.dynamic_batch_generator import DynamicBatchGenerationError, generate_batch
from app.services.dynamic_fields import (
    FieldValidationError,
    parse_field_values,
    parse_recipients_from_csv,
    parse_recipients_from_list,
)
from app.services.letter_type_repo import get_letter_type_with_fields, split_fields_by_level
from app.services.pdf_merger import PdfMergeError

router = APIRouter(prefix="/generate", tags=["Generate Surat Dinamis"])


def _parse_base_info(raw: dict) -> dict:
    """
    Validasi & convert field universal yang berlaku untuk semua jenis surat
    (nomor_surat, tempat_surat, tanggal_surat, perihal_surat, lampirans).
    """
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
            tanggal_surat = datetime.strptime(str(tanggal_surat_raw).strip(), "%Y-%m-%d").date()
        except ValueError:
            errors.append("'Tanggal Surat' harus berupa tanggal dengan format YYYY-MM-DD.")

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
    except Exception as e:
        job_store.mark_error(job_id, f"Terjadi kesalahan tidak terduga: {e}")
        shutil.rmtree(working_dir, ignore_errors=True)


@router.post("/{slug}")
def start_generate_job(
    slug: str,
    background_tasks: BackgroundTasks,
    batch_info: str = Form(...),
    recipients_mode: str = Form(...),
    lampiran_files: list[UploadFile] | None = File(default=None),
    recipients_json: str | None = Form(default=None),
    recipients_csv: UploadFile | None = File(default=None),
):
    with Session(engine) as session:
        result = get_letter_type_with_fields(session, slug)
    if not result:
        raise HTTPException(status_code=404, detail="Jenis surat tidak ditemukan.")

    letter_type, fields = result
    batch_fields, recipient_fields = split_fields_by_level(fields)

    lampiran_files = lampiran_files or []
    job_id = uuid.uuid4().hex
    working_dir = Path(settings.temp_dir) / f"job_{job_id}"
    working_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            batch_info_raw = json.loads(batch_info)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"batch_info bukan JSON valid: {e}")

        base_info = _parse_base_info(batch_info_raw)
        custom_batch_values = parse_field_values(
            batch_info_raw.get("custom_fields", {}), batch_fields, "Informasi surat"
        )

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
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)
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
    except Exception as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan tidak terduga: {e}")

    job_store.create_job(job_id=job_id, total=len(recipients))
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


@router.get("/jobs/{job_id}/status")
def get_job_status(job_id: str):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return job


@router.get("/jobs/{job_id}/download")
def download_job_result(job_id: str, background_tasks: BackgroundTasks):
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
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
