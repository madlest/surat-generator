"""
Stage B4 — _validate_email_config: aturan saat kirim email diaktifkan untuk
sebuah jenis surat.
"""
import pytest
from fastapi import HTTPException

from app.routers.admin import _validate_email_config

EMAIL_FIELD = {"field_type": "email", "level": "recipient"}
NAME_FIELD = {"field_type": "text", "level": "recipient"}


def test_nonaktif_simpan_apa_adanya():
    enabled, subject, body = _validate_email_config("false", " Hai ", "", [NAME_FIELD])
    assert enabled is False
    assert subject == "Hai"
    assert body is None  # string kosong -> None


def test_aktif_butuh_tepat_satu_field_email_recipient():
    with pytest.raises(HTTPException) as ei:
        _validate_email_config("true", "S", "B", [NAME_FIELD])
    assert ei.value.status_code == 400

    with pytest.raises(HTTPException):
        _validate_email_config("true", "S", "B", [EMAIL_FIELD, dict(EMAIL_FIELD)])


def test_aktif_email_field_harus_level_recipient():
    batch_email = {"field_type": "email", "level": "batch"}
    with pytest.raises(HTTPException):
        _validate_email_config("true", "S", "B", [batch_email])


def test_aktif_subjek_dan_isi_wajib():
    with pytest.raises(HTTPException):
        _validate_email_config("true", "", "B", [EMAIL_FIELD])
    with pytest.raises(HTTPException):
        _validate_email_config("true", "S", "   ", [EMAIL_FIELD])


def test_aktif_valid():
    enabled, subject, body = _validate_email_config(
        "1", "Surat {nama}", "Halo {nama}", [NAME_FIELD, EMAIL_FIELD]
    )
    assert (enabled, subject, body) == (True, "Surat {nama}", "Halo {nama}")
