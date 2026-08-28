"""
Stage A — _normalize_fields_config menerima field manual (from_template=False)
dan filled_by, dengan validasi key & filled_by.
"""
import json

import pytest
from fastapi import HTTPException

from app.routers.admin import _normalize_fields_config


def _cfg(*fields):
    return json.dumps(list(fields))


def test_field_template_default_from_template_true_filled_by_admin():
    out = _normalize_fields_config(_cfg({"field_key": "nama_dosen", "level": "recipient"}))
    assert out[0]["from_template"] is True
    assert out[0]["filled_by"] == "admin"


def test_field_manual_diterima():
    out = _normalize_fields_config(
        _cfg(
            {"field_key": "nama_dosen", "level": "recipient"},
            {
                "field_key": "nomor_wa",
                "label": "Nomor WhatsApp",
                "field_type": "phone",
                "level": "recipient",
                "from_template": False,
            },
        )
    )
    manual = out[1]
    assert manual["from_template"] is False
    assert manual["field_type"] == "phone"
    assert manual["filled_by"] == "admin"


@pytest.mark.parametrize("bad_key", ["Nomor WA", "nomor.wa", "nomor wa", "-nomorwa"])
def test_key_field_manual_tidak_bersih_ditolak(bad_key):
    with pytest.raises(HTTPException) as exc:
        _normalize_fields_config(
            _cfg({"field_key": bad_key, "level": "recipient", "from_template": False})
        )
    assert exc.value.status_code == 400


def test_key_field_manual_boleh_underscore():
    out = _normalize_fields_config(
        _cfg({"field_key": "nomor_wa_dosen", "level": "recipient", "from_template": False})
    )
    assert out[0]["field_key"] == "nomor_wa_dosen"


def test_filled_by_tidak_dikenal_ditolak():
    with pytest.raises(HTTPException) as exc:
        _normalize_fields_config(
            _cfg({"field_key": "x", "level": "recipient", "filled_by": "dukun"})
        )
    assert exc.value.status_code == 400


def test_filled_by_student_diterima():
    out = _normalize_fields_config(
        _cfg({"field_key": "nim", "level": "recipient", "filled_by": "student"})
    )
    assert out[0]["filled_by"] == "student"


def test_tipe_email_phone_dikenal():
    out = _normalize_fields_config(
        _cfg(
            {"field_key": "a", "level": "batch", "field_type": "email"},
            {"field_key": "b", "level": "recipient", "field_type": "phone"},
        )
    )
    assert [f["field_type"] for f in out] == ["email", "phone"]


def test_key_duplikat_ditolak():
    with pytest.raises(HTTPException):
        _normalize_fields_config(
            _cfg(
                {"field_key": "x", "level": "recipient"},
                {"field_key": "x", "level": "recipient", "from_template": False},
            )
        )
