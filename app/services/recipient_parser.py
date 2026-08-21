# Parser untuk mengubah data recipient dari berbagai format ke model Pydantic

import csv
import io
from pydantic import ValidationError

from app.models.permohonan_mengajar import PermohonanMengajarRecipient


class RecipientParseError(Exception):
    """Raised ketika ada baris CSV yang gagal divalidasi jadi Recipient."""
    def __init__(self, row_number: int, errors: list[dict]):
        self.row_number = row_number
        self.errors = errors
        pesan_error = "; ".join(
            f"{err['loc'][0]}: {err['msg']}" for err in errors
        )
        super().__init__(f"Baris CSV ke-{row_number} tidak valid: {pesan_error}")


def parse_recipients_from_csv(file_content: bytes) -> list[PermohonanMengajarRecipient]:
    """
    Ubah isi file CSV (dalam bentuk bytes, dari upload) jadi list
    PermohonanMengajarRecipient yang sudah tervalidasi.

    Header CSV yang diharapkan (persis, case-sensitive):
        nama_dosen,mata_kuliah,semester

    Kalau ada baris yang gagal validasi, proses langsung berhenti
    (fail-fast) dan raise RecipientParseError yang menyebutkan baris
    ke berapa dan kenapa gagal.
    """
    # utf-8-sig supaya toleran terhadap BOM yang sering disisipkan Excel
    text_stream = io.StringIO(file_content.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)

    if reader.fieldnames is None:
        raise ValueError("File CSV kosong atau tidak punya header.")

    kolom_wajib = {"nama_dosen", "mata_kuliah", "semester"}
    kolom_ada = set(reader.fieldnames)
    kolom_hilang = kolom_wajib - kolom_ada
    if kolom_hilang:
        raise ValueError(
            f"Kolom CSV berikut tidak ditemukan: {', '.join(kolom_hilang)}. "
            f"Kolom yang terdeteksi: {', '.join(reader.fieldnames)}"
        )

    recipients: list[PermohonanMengajarRecipient] = []

    # enumerate mulai dari 2 karena baris 1 adalah header,
    # jadi baris data pertama = baris 2 di file aslinya
    for row_number, row in enumerate(reader, start=2):
        # buang whitespace nyasar di tiap value, biar " V " tetap kebaca "V"
        row_bersih = {k: (v.strip() if v else v) for k, v in row.items()}

        try:
            recipient = PermohonanMengajarRecipient(**row_bersih)
        except ValidationError as e:
            raise RecipientParseError(row_number, e.errors()) from e

        recipients.append(recipient)

    if not recipients:
        raise ValueError("CSV tidak berisi data recipient sama sekali (cuma header).")

    return recipients


def parse_recipients_from_list(
    recipients_data: list[dict],
) -> list[PermohonanMengajarRecipient]:
    """
    Untuk mode input 'list langsung'. Sebenarnya kalau kamu terima ini
    lewat FastAPI request body yang sudah pakai PermohonanMengajarRequest,
    validasi ini SUDAH otomatis terjadi oleh FastAPI sebelum masuk sini.

    Fungsi ini disediakan untuk kasus kamu terima data mentah (dict) di
    luar jalur request body FastAPI biasa — misal dipanggil langsung dari
    script/test, bukan dari endpoint.
    """
    recipients: list[PermohonanMengajarRecipient] = []

    for index, item in enumerate(recipients_data, start=1):
        try:
            recipient = PermohonanMengajarRecipient(**item)
        except ValidationError as e:
            raise RecipientParseError(index, e.errors()) from e
        recipients.append(recipient)

    return recipients