"""
_validate_email_config (Stage B4) & _validate_whatsapp_config (Stage C):
aturan saat kanal kirim diaktifkan untuk sebuah jenis surat.
"""
import pytest
from fastapi import HTTPException

from app.routers.admin import _validate_email_config, _validate_whatsapp_config

EMAIL_FIELD = {"field_type": "email", "level": "recipient"}
PHONE_FIELD = {"field_type": "phone", "level": "recipient"}
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


# --- WhatsApp ----------------------------------------------------------

def test_wa_nonaktif_simpan_apa_adanya():
    enabled, msg = _validate_whatsapp_config("false", " hai ", [NAME_FIELD])
    assert (enabled, msg) == (False, "hai")


def test_wa_aktif_butuh_tepat_satu_field_phone_recipient():
    with pytest.raises(HTTPException):
        _validate_whatsapp_config("true", "hai", [NAME_FIELD])
    with pytest.raises(HTTPException):
        _validate_whatsapp_config("true", "hai", [PHONE_FIELD, dict(PHONE_FIELD)])
    with pytest.raises(HTTPException):
        _validate_whatsapp_config("true", "hai", [{"field_type": "phone", "level": "batch"}])


def test_wa_aktif_pesan_wajib():
    with pytest.raises(HTTPException):
        _validate_whatsapp_config("true", "  ", [PHONE_FIELD])


def test_wa_aktif_valid():
    assert _validate_whatsapp_config("1", "Halo {nama}", [NAME_FIELD, PHONE_FIELD]) == (
        True,
        "Halo {nama}",
    )
