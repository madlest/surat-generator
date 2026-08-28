"""
Stage A — field manual (from_template=False) TIDAK diinjeksikan ke context
docxtpl, dan tidak ikut menyusun label/nama file penerima. Nilainya tetap ada
di data mentah (untuk pengiriman nanti).
"""
from datetime import date

from app.models.letter_type import FieldLevel, FieldType, LetterField
from app.services.dynamic_batch_generator import _build_recipient_label, build_context


def _f(key, field_type=FieldType.text, level=FieldLevel.recipient, from_template=True):
    return LetterField(
        field_key=key, label=key, field_type=field_type, level=level,
        required=False, from_template=from_template,
    )


BASE_INFO = {
    "nomor_surat": "001/X/2026",
    "tempat_surat": "Banjarmasin",
    "tanggal_surat": date(2026, 1, 2),
    "perihal_surat": "Uji",
    "lampirans": [],
}


def test_field_manual_tidak_masuk_context():
    recipient_fields = [
        _f("nama_dosen"),
        _f("nomor_wa", FieldType.phone, from_template=False),
    ]
    ctx = build_context(
        BASE_INFO,
        custom_batch_values={},
        batch_fields=[],
        recipient_values={"nama_dosen": "Dr. Budi", "nomor_wa": "+6281234567890"},
        recipient_fields=recipient_fields,
    )
    assert ctx["nama_dosen"] == "Dr. Budi"
    assert "nomor_wa" not in ctx


def test_field_manual_batch_juga_dikecualikan():
    batch_fields = [_f("email_tembusan", FieldType.email, FieldLevel.batch, from_template=False)]
    ctx = build_context(
        BASE_INFO,
        custom_batch_values={"email_tembusan": "tu@umbjm.ac.id"},
        batch_fields=batch_fields,
        recipient_values={},
        recipient_fields=[],
    )
    assert "email_tembusan" not in ctx


def test_label_penerima_abaikan_field_manual():
    recipient_fields = [
        _f("nama_dosen"),
        _f("nomor_wa", FieldType.phone, from_template=False),
    ]
    label = _build_recipient_label(
        {"nama_dosen": "Dr. Budi", "nomor_wa": "+6281234567890"}, recipient_fields
    )
    assert label == "Dr. Budi"
