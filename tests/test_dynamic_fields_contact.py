"""
Stage A — tipe field kontak: validasi email & normalisasi nomor HP Indonesia
lewat parse_field_value / parse_field_values (jalur form & CSV sama).
"""
import pytest

from app.models.letter_type import FieldLevel, FieldType, LetterField
from app.services.dynamic_fields import (
    FieldValidationError,
    normalize_phone_id,
    parse_field_value,
    parse_recipients_from_csv,
    validate_email,
)


def _field(field_type, key="kontak", required=True):
    return LetterField(
        field_key=key, label=key.replace("_", " ").title(),
        field_type=field_type, level=FieldLevel.recipient, required=required,
    )


# --- normalisasi nomor HP ----------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("081234567890", "+6281234567890"),
        ("81234567890", "+6281234567890"),
        ("6281234567890", "+6281234567890"),
        ("+6281234567890", "+6281234567890"),
        ("+62 812-3456-7890", "+6281234567890"),
        ("(0812) 3456 789", "+628123456789"),
        ("006281234567890", "+6281234567890"),
    ],
)
def test_normalisasi_nomor_hp(raw, expected):
    assert normalize_phone_id(raw, "Nomor WA") == expected


@pytest.mark.parametrize(
    "raw",
    [
        "021234567",       # bukan diawali 8
        "0812345",         # terlalu pendek
        "0812345678901234",  # terlalu panjang
        "bukan-nomor",
        "",
    ],
)
def test_nomor_hp_tidak_valid_ditolak(raw):
    with pytest.raises(ValueError):
        normalize_phone_id(raw, "Nomor WA")


def test_phone_lewat_parse_field_value():
    assert parse_field_value("0812-3456-7890", _field(FieldType.phone)) == "+6281234567890"


def test_phone_kosong_opsional_jadi_none():
    assert parse_field_value("", _field(FieldType.phone, required=False)) is None


# --- validasi email --------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("a@b.co", "a@b.co"),
    ("  Dosen@UMBJM.ac.id ", "dosen@umbjm.ac.id"),
])
def test_email_valid_dinormalisasi_lowercase(raw, expected):
    assert validate_email(raw, "Email") == expected


@pytest.mark.parametrize("raw", ["bukanemail", "a@b", "a b@c.com", "@x.com"])
def test_email_tidak_valid_ditolak(raw):
    with pytest.raises(ValueError):
        validate_email(raw, "Email")


def test_email_lewat_parse_field_value():
    assert parse_field_value("X@Y.COM", _field(FieldType.email)) == "x@y.com"


# --- lewat CSV -------------------------------------------------------

def test_csv_kolom_phone_dinormalisasi():
    fields = [
        _field(FieldType.text, "nama"),
        _field(FieldType.phone, "nomor_wa"),
    ]
    csv = b"nama,nomor_wa\nBudi,081234567890\nSiti,+62 813 0000 1111\n"
    rows = parse_recipients_from_csv(csv, fields)
    assert rows[0]["nomor_wa"] == "+6281234567890"
    assert rows[1]["nomor_wa"] == "+6281300001111"


def test_csv_phone_salah_error_per_baris():
    fields = [_field(FieldType.phone, "nomor_wa")]
    csv = b"nomor_wa\n081234567890\n021-bukan-hp\n"
    with pytest.raises(FieldValidationError) as exc:
        parse_recipients_from_csv(csv, fields)
    assert "Baris CSV ke-3" in str(exc.value)
