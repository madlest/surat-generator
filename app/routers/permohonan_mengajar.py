import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.core.config import settings
from app.core.job_store import job_store
from app.models.permohonan_mengajar import PermohonanMengajarBatchInfo
from app.services.batch_generator import BatchGenerationError, generate_batch
from app.services.document_generator import DocumentGenerationError
from app.services.pdf_merger import PdfMergeError
from app.services.recipient_parser import (
    RecipientParseError,
    parse_recipients_from_csv,
    parse_recipients_from_list,
)

router = APIRouter(prefix="/surat/permohonan-mengajar", tags=["Permohonan Mengajar"])

TEMPLATE_PATH = "app/templates/template_spm_generate.docx"


def _run_batch_job(job_id: str, batch_info_obj, recipients, working_dir: str):
    """
    Dijalankan di background SETELAH response awal (job_id) sudah
    dikirim ke client. Update job_store tiap recipient selesai,
    supaya bisa dilacak lewat endpoint /jobs/{job_id}/status.
    """
    try:
        def on_progress(current: int, total: int):
            job_store.update_progress(job_id, current)

        zip_path = generate_batch(
            template_path=TEMPLATE_PATH,
            batch_info=batch_info_obj,
            recipients=recipients,
            working_dir=working_dir,
            progress_callback=on_progress,
        )
        job_store.mark_done(job_id, zip_path)
    except (DocumentGenerationError, PdfMergeError, BatchGenerationError) as e:
        job_store.mark_error(job_id, str(e))
        shutil.rmtree(working_dir, ignore_errors=True)
    except Exception as e:
        job_store.mark_error(job_id, f"Terjadi kesalahan tidak terduga: {e}")
        shutil.rmtree(working_dir, ignore_errors=True)


@router.post("/generate")
def start_generate_job(
    background_tasks: BackgroundTasks,
    batch_info: str = Form(...),
    recipients_mode: str = Form(...),
    lampiran_files: list[UploadFile] | None = File(default=None),
    recipients_json: str | None = Form(default=None),
    recipients_csv: UploadFile | None = File(default=None),
):
    lampiran_files = lampiran_files or []
    job_id = uuid.uuid4().hex
    working_dir = Path(settings.temp_dir) / f"job_{job_id}"
    working_dir.mkdir(parents=True, exist_ok=True)

    try:
        try:
            batch_info_dict = json.loads(batch_info)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"batch_info bukan JSON valid: {e}")

        try:
            batch_info_obj = PermohonanMengajarBatchInfo(**batch_info_dict)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

        if len(lampiran_files) != len(batch_info_obj.lampirans):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Jumlah file lampiran ({len(lampiran_files)}) tidak sama dengan "
                    f"jumlah judul lampiran ({len(batch_info_obj.lampirans)})."
                ),
            )

        lampiran_dir = working_dir / "lampiran"
        lampiran_dir.mkdir(parents=True, exist_ok=True)
        for index, upload_file in enumerate(lampiran_files):
            dest_path = lampiran_dir / f"lampiran_{index}.pdf"
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)
            batch_info_obj.lampirans[index].file_path = str(dest_path)

        if recipients_mode == "list":
            if not recipients_json:
                raise HTTPException(status_code=400, detail="recipients_json wajib diisi untuk mode 'list'.")
            try:
                recipients_data = json.loads(recipients_json)
            except json.JSONDecodeError as e:
                raise HTTPException(status_code=400, detail=f"recipients_json bukan JSON valid: {e}")
            recipients = parse_recipients_from_list(recipients_data)

        elif recipients_mode == "csv":
            if recipients_csv is None:
                raise HTTPException(status_code=400, detail="recipients_csv wajib diupload untuk mode 'csv'.")
            content = recipients_csv.file.read()
            recipients = parse_recipients_from_csv(content)

        else:
            raise HTTPException(status_code=400, detail="recipients_mode harus 'list' atau 'csv'.")

    except RecipientParseError as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan tidak terduga: {e}")

    # Validasi & penyimpanan file (cepat) sudah selesai di sini.
    # Proses berat (generate + convert PDF per recipient) didaftarkan
    # sebagai background task, supaya response ini bisa langsung
    # kembali ke client tanpa menunggu semuanya selesai.
    job_store.create_job(job_id=job_id, total=len(recipients))
    background_tasks.add_task(
        _run_batch_job, job_id, batch_info_obj, recipients, str(working_dir)
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
        filename="hasil_surat_permohonan_mengajar.zip",
        background=background_tasks,
    )