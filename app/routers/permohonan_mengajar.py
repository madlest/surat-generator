# Fungsi ini menerima permintaan untuk menghasilkan
# dokumen permohonan mengajar (cover letter + lampiran) untuk banyak recipient,
# lalu menggabungkan hasilnya menjadi satu file zip yang bisa diunduh.

import json
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import ValidationError

from app.core.config import settings
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


@router.post("/generate")
def generate_surat_permohonan_mengajar(
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
        # 1. Parse & validasi batch_info (dikirim sebagai JSON string)
        try:
            batch_info_dict = json.loads(batch_info)
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"batch_info bukan JSON valid: {e}")

        try:
            batch_info_obj = PermohonanMengajarBatchInfo(**batch_info_dict)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors())

        # 2. Jumlah file lampiran harus cocok dengan jumlah judul lampiran
        if len(lampiran_files) != len(batch_info_obj.lampirans):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Jumlah file lampiran ({len(lampiran_files)}) tidak sama dengan "
                    f"jumlah judul lampiran ({len(batch_info_obj.lampirans)})."
                ),
            )

        # 3. Simpan file lampiran ke working_dir, isi file_path tiap LampiranItem
        #    (urutan file HARUS sejajar dengan urutan lampirans di batch_info)
        lampiran_dir = working_dir / "lampiran"
        lampiran_dir.mkdir(parents=True, exist_ok=True)

        for index, upload_file in enumerate(lampiran_files):
            dest_path = lampiran_dir / f"lampiran_{index}.pdf"
            with open(dest_path, "wb") as f:
                shutil.copyfileobj(upload_file.file, f)
            batch_info_obj.lampirans[index].file_path = str(dest_path)

        # 4. Parse recipients sesuai mode yang dipilih
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

        # 5. Generate seluruh batch
        zip_path = generate_batch(
            template_path=TEMPLATE_PATH,
            batch_info=batch_info_obj,
            recipients=recipients,
            working_dir=str(working_dir),
        )

    except (RecipientParseError, DocumentGenerationError, PdfMergeError, BatchGenerationError) as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=str(e))
    except HTTPException:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise
    except Exception as e:
        shutil.rmtree(working_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan tidak terduga: {e}")

    # Folder kerja dihapus otomatis SETELAH file zip selesai dikirim ke client
    background_tasks.add_task(shutil.rmtree, working_dir, ignore_errors=True)

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename="hasil_surat_permohonan_mengajar.zip",
        background=background_tasks,
    )