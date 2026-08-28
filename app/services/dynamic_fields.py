# Validasi & parsing nilai field custom (LetterField) untuk jenis surat dinamis.

import csv
import io
import re
from datetime import datetime

from app.models.letter_type import FieldType, LetterField


# Sengaja longgar: validasi email yang sebenarnya adalah "apakah kirimannya
# nyampe" — itu baru ketahuan saat pengiriman. Di sini cukup menyaring
# kesalahan ketik yang jelas.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Karakter pemisah yang lazim diketik orang di nomor telepon.
_PHONE_SEP_RE = re.compile(r"[\s\-().]")


def validate_email(raw: str, label: str) -> str:
    email = str(raw).strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError(f"'{label}' bukan alamat email yang valid.")
    return email


def normalize_phone_id(raw: str, label: str) -> str:
    """
    Normalisasi nomor HP Indonesia ke format E.164 (+62…). Menerima 08xx,
    8xx, +62xx, 62xx, 0062xx, dengan/atau tanpa spasi/strip/kurung.
    """
    cleaned = _PHONE_SEP_RE.sub("", str(raw).strip())

    if cleaned.startswith("+62"):
        national = cleaned[3:]
    elif cleaned.startswith("0062"):
        national = cleaned[4:]
    elif cleaned.startswith("62"):
        national = cleaned[2:]
    elif cleaned.startswith("0"):
        national = cleaned[1:]
    else:
        national = cleaned

    if not national.isdigit():
        raise ValueError(f"'{label}' hanya boleh berisi angka (dan opsional +62 / 08 di depan).")
    if not national.startswith("8"):
        raise ValueError(f"'{label}' sepertinya bukan nomor HP Indonesia — harus diawali 08 atau +62 8.")
    if not (9 <= len(national) <= 12):
        raise ValueError(f"'{label}' panjang nomornya tidak wajar untuk nomor HP Indonesia.")

    return "+62" + national


class FieldValidationError(Exception):
    """Raised ketika satu atau lebih nilai field custom gagal divalidasi."""

    def __init__(self, context_label: str, errors: list[str]):
        self.context_label = context_label
        self.errors = errors
        super().__init__(f"{context_label}: {'; '.join(errors)}")


def parse_field_value(raw_value, field: LetterField):
    """
    Ubah satu nilai mentah (string dari form/CSV) jadi tipe Python sesuai
    field.field_type, sambil menegakkan field.required.

    Catatan format tanggal: fungsi ini selalu expect ISO (YYYY-MM-DD).
    Titik masuk manapun (Mode List via native date picker, atau Mode CSV)
    wajib sudah dinormalisasi ke ISO sebelum sampai sini — lihat
    _normalize_csv_date untuk jalur CSV.
    """
    if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
        if field.required:
            raise ValueError(f"'{field.label}' wajib diisi.")
        return None

    if field.field_type == FieldType.date:
        try:
            return datetime.strptime(str(raw_value).strip(), "%Y-%m-%d").date()
        except ValueError:
            raise ValueError(f"'{field.label}' harus berupa tanggal dengan format DD-MM-YYYY.")

    if field.field_type == FieldType.number:
        value_str = str(raw_value).strip()
        try:
            return int(value_str)
        except ValueError:
            try:
                return float(value_str)
            except ValueError:
                raise ValueError(f"'{field.label}' harus berupa angka.")

    if field.field_type == FieldType.email:
        return validate_email(raw_value, field.label)

    if field.field_type == FieldType.phone:
        return normalize_phone_id(raw_value, field.label)

    return str(raw_value).strip()


def parse_field_values(raw_values: dict, fields: list[LetterField], context_label: str) -> dict:
    """
    Validasi & convert satu set nilai (dict field_key -> raw value) terhadap
    daftar LetterField yang relevan. Fail-fast per context_label (kumpulkan
    semua error dulu, baru raise) supaya pesan error informatif.
    """
    result: dict = {}
    errors: list[str] = []
    for field in fields:
        try:
            result[field.field_key] = parse_field_value(raw_values.get(field.field_key), field)
        except ValueError as e:
            errors.append(str(e))

    if errors:
        raise FieldValidationError(context_label, errors)

    return result


def parse_recipients_from_list(recipients_data: list[dict], recipient_fields: list[LetterField]) -> list[dict]:
    recipients = []
    for index, item in enumerate(recipients_data, start=1):
        recipients.append(parse_field_values(item, recipient_fields, f"Penerima ke-{index}"))
    return recipients


def _normalize_csv_date(raw_value: str | None) -> str | None:
    """
    CSV minta user isi tanggal format DD-MM-YYYY (lebih familiar untuk
    orang Indonesia), tapi parse_field_value expect YYYY-MM-DD (format
    yang juga dikirim native date picker di Mode List). Fungsi ini
    menjembatani keduanya di titik masuk CSV saja.
    """
    if raw_value is None or raw_value.strip() == "":
        return raw_value
    try:
        return datetime.strptime(raw_value.strip(), "%d-%m-%Y").strftime("%Y-%m-%d")
    except ValueError:
        # Biarkan lolos apa adanya kalau tidak match format DD-MM-YYYY —
        # nanti parse_field_value yang akan raise error yang informatif.
        return raw_value


def parse_recipients_from_csv(file_content: bytes, recipient_fields: list[LetterField]) -> list[dict]:
    """
    Header CSV yang diharapkan: persis field_key tiap LetterField level
    recipient (case-sensitive). Untuk field bertipe date, isi kolom dengan
    format DD-MM-YYYY.
    """
    text_stream = io.StringIO(file_content.decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)

    if reader.fieldnames is None:
        raise ValueError("File CSV kosong atau tidak punya header.")

    kolom_wajib = {field.field_key for field in recipient_fields}
    kolom_ada = set(reader.fieldnames)
    kolom_hilang = kolom_wajib - kolom_ada
    if kolom_hilang:
        raise ValueError(
            f"Kolom CSV berikut tidak ditemukan: {', '.join(kolom_hilang)}. "
            f"Kolom yang terdeteksi: {', '.join(reader.fieldnames)}"
        )

    date_field_keys = {field.field_key for field in recipient_fields if field.field_type == FieldType.date}

    recipients = []
    for row_number, row in enumerate(reader, start=2):
        row_bersih = {k: (v.strip() if v else v) for k, v in row.items()}

        # Normalisasi kolom date dari DD-MM-YYYY (format yang diminta ke user)
        # ke YYYY-MM-DD (format yang dipahami parse_field_value), supaya
        # logic parsing tanggal tetap satu jalur dengan Mode List.
        for key in date_field_keys:
            row_bersih[key] = _normalize_csv_date(row_bersih.get(key))

        recipients.append(parse_field_values(row_bersih, recipient_fields, f"Baris CSV ke-{row_number}"))

    if not recipients:
        raise ValueError("CSV tidak berisi data recipient sama sekali (cuma header).")

    return recipients