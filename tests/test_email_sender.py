"""app/services/email_sender.py — kirim email via Gmail API (Model B).

Jaringan di-mock lewat monkeypatch httpx.post; test memeriksa penanganan
status + bentuk MIME yang dirakit.
"""
import base64
import email
import json as _json
from email import policy

import httpx
import pytest

from app.services import email_sender
from app.services.email_sender import (
    EmailSenderError,
    EmailTooLarge,
    GmailAuthExpired,
    build_raw_message,
    send_email,
)


class FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text or (_json.dumps(payload) if payload is not None else "")

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture()
def gmail_http(monkeypatch):
    """Rekam panggilan httpx.post dan balas dengan respons yang bisa diatur
    per test. Kunci: 'token' (endpoint refresh) & 'send' (Gmail send)."""
    calls = []
    responses = {
        "token": FakeResp(200, {"access_token": "ya29.fake"}),
        "send": FakeResp(200, {"id": "msg-123"}),
    }

    def fake_post(url, **kwargs):
        key = "token" if "oauth2" in url else "send"
        calls.append({"url": url, "key": key, **kwargs})
        return responses[key]

    monkeypatch.setattr(email_sender.httpx, "post", fake_post)
    return {"calls": calls, "responses": responses}


def _decode(raw_b64):
    return email.message_from_bytes(base64.urlsafe_b64decode(raw_b64), policy=policy.default)


# --- build_raw_message ---------------------------------------------------

def test_raw_message_berisi_header_dan_lampiran():
    raw = build_raw_message(
        "admin@umbjm.ac.id", "tujuan@contoh.com", "Surat Anda", "Halo,\nterlampir.",
        [("surat_budi.pdf", b"%PDF-1.4 fake")],
    )
    msg = _decode(raw)
    assert msg["To"] == "tujuan@contoh.com"
    assert msg["From"] == "admin@umbjm.ac.id"
    assert msg["Subject"] == "Surat Anda"
    parts = list(msg.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "surat_budi.pdf"
    assert parts[0].get_payload(decode=True) == b"%PDF-1.4 fake"


def test_lampiran_kegedean_tolak_sebelum_kirim(gmail_http):
    big = b"x" * (email_sender.MAX_MESSAGE_BYTES + 1)
    with pytest.raises(EmailTooLarge):
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b", attachments=[("big.pdf", big)],
        )
    assert gmail_http["calls"] == []  # tidak ada panggilan ke Google


# --- send_email: jalur sukses -----------------------------------------

def test_send_sukses_mengembalikan_message_id(gmail_http):
    mid = send_email(
        refresh_token="r-tok", sender="admin@umbjm.ac.id", to="tujuan@contoh.com",
        subject="Hi", body_text="isi", attachments=[("a.pdf", b"%PDF-")],
    )
    assert mid == "msg-123"
    keys = [c["key"] for c in gmail_http["calls"]]
    assert keys == ["token", "send"]
    send_call = gmail_http["calls"][1]
    assert send_call["headers"]["Authorization"] == "Bearer ya29.fake"
    assert "raw" in send_call["json"]


# --- send_email: kegagalan -------------------------------------------

def test_refresh_invalid_grant_jadi_auth_expired(gmail_http):
    gmail_http["responses"]["token"] = FakeResp(400, {"error": "invalid_grant"})
    with pytest.raises(GmailAuthExpired):
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b",
        )


def test_refresh_error_lain_jadi_sender_error(gmail_http):
    gmail_http["responses"]["token"] = FakeResp(500, text="boom")
    with pytest.raises(EmailSenderError) as ei:
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b",
        )
    assert not isinstance(ei.value, GmailAuthExpired)


def test_send_403_jadi_auth_expired(gmail_http):
    gmail_http["responses"]["send"] = FakeResp(403, {"error": {"message": "insufficient"}})
    with pytest.raises(GmailAuthExpired):
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b",
        )


def test_send_500_jadi_sender_error(gmail_http):
    gmail_http["responses"]["send"] = FakeResp(500, text="server error")
    with pytest.raises(EmailSenderError) as ei:
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b",
        )
    assert not isinstance(ei.value, GmailAuthExpired)


def test_network_error_jadi_sender_error(gmail_http, monkeypatch):
    def boom(url, **kwargs):
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(email_sender.httpx, "post", boom)
    with pytest.raises(EmailSenderError):
        send_email(
            refresh_token="r", sender="a@umbjm.ac.id", to="b@c.com",
            subject="s", body_text="b",
        )
