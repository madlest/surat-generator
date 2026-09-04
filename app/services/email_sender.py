"""
Kirim email lewat Gmail API sebagai admin yang sedang login (Model B): memakai
refresh token OAuth per-admin yang tersimpan TERENKRIPSI di
`User.gmail_refresh_token_enc` (lihat alur "Hubungkan Gmail" di
app/routers/auth.py). Tidak ada SMTP, tidak ada password.

Fungsi di modul ini murni: terima refresh token + isi email, kembalikan id
pesan Gmail atau lempar exception. Tidak menyentuh DB / job_store — orkestrasi
(dedupe per tujuan, status per penerima, retry) ada di Stage B4.

HTTP-nya sinkron (`httpx.post` level-modul) karena pemanggilnya berjalan
sebagai background task Starlette di threadpool, sama polanya dengan
_run_batch_job di generate.py.
"""
from __future__ import annotations

import base64
from email.message import EmailMessage

import httpx

from app.core.config import settings
from app.core.oauth import GOOGLE_TOKEN_ENDPOINT

GMAIL_SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

# Gmail API `messages.send` (non-resumable) menerima pesan mentah hingga ~35 MB;
# base64 menggelembungkan ~33% sehingga isi efektif ~26 MB. Diambil 25 MB
# dengan margin. Dicek sebelum token diminta, supaya lampiran kegedean gagal
# cepat tanpa memanggil Google.
MAX_MESSAGE_BYTES = 25 * 1024 * 1024


class EmailSenderError(Exception):
    """Kegagalan umum saat mengirim email. Boleh di-retry."""


class GmailAuthExpired(EmailSenderError):
    """Refresh / access token ditolak Google (user mencabut izin, app kembali
    ke status Testing, scope dicabut, dst). Admin harus menghubungkan ulang
    Gmail — retry tidak akan menolong."""


class EmailTooLarge(EmailSenderError):
    """Total lampiran melebihi batas Gmail API. Retry tidak menolong."""


def _json_error_code(resp: httpx.Response) -> str | None:
    try:
        return resp.json().get("error")
    except (ValueError, AttributeError):
        return None


def _access_token_from_refresh(refresh_token: str) -> str:
    try:
        resp = httpx.post(
            GOOGLE_TOKEN_ENDPOINT,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        raise EmailSenderError(f"Gagal menghubungi Google untuk menyegarkan token: {exc}") from exc

    if resp.status_code == 400 and _json_error_code(resp) == "invalid_grant":
        raise GmailAuthExpired(
            "Izin Gmail sudah tidak berlaku. Hubungkan ulang Gmail lewat menu, "
            "lalu kirim lagi."
        )
    if resp.status_code != 200:
        raise EmailSenderError(
            f"Google menolak permintaan penyegaran token (HTTP {resp.status_code})."
        )

    token = resp.json().get("access_token")
    if not token:
        raise EmailSenderError("Respons token Google tidak berisi access_token.")
    return token


def build_raw_message(
    sender: str,
    to: str,
    subject: str,
    body_text: str,
    attachments: list[tuple[str, bytes]],
) -> str:
    """Rakit MIME lalu encode base64url sesuai format `raw` Gmail API. Dipisah
    supaya bisa diuji tanpa jaringan. Melempar EmailTooLarge kalau hasilnya
    melebihi MAX_MESSAGE_BYTES."""
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body_text)

    for filename, content in attachments:
        msg.add_attachment(content, maintype="application", subtype="pdf", filename=filename)

    raw_bytes = msg.as_bytes()
    if len(raw_bytes) > MAX_MESSAGE_BYTES:
        raise EmailTooLarge(
            "Total lampiran terlalu besar untuk dikirim via email "
            f"(maksimum sekitar {MAX_MESSAGE_BYTES // (1024 * 1024)} MB). "
            "Kurangi jumlah surat per penerima atau kirim terpisah."
        )
    return base64.urlsafe_b64encode(raw_bytes).decode()


def send_email(
    *,
    refresh_token: str,
    sender: str,
    to: str,
    subject: str,
    body_text: str,
    attachments: list[tuple[str, bytes]] | None = None,
) -> str:
    """Kirim satu email lewat akun Gmail pemilik `refresh_token`. Mengembalikan
    id pesan Gmail.

    - GmailAuthExpired  → izin harus diperbarui (jangan di-retry)
    - EmailTooLarge     → lampiran kegedean (jangan di-retry)
    - EmailSenderError  → kegagalan lain (boleh di-retry)
    """
    raw = build_raw_message(sender, to, subject, body_text, attachments or [])
    access_token = _access_token_from_refresh(refresh_token)

    try:
        resp = httpx.post(
            GMAIL_SEND_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            json={"raw": raw},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise EmailSenderError(f"Gagal menghubungi Gmail API: {exc}") from exc

    if resp.status_code in (401, 403):
        raise GmailAuthExpired(
            "Gmail menolak permintaan kirim (izin tidak mencukupi). Hubungkan ulang Gmail."
        )
    if resp.status_code != 200:
        raise EmailSenderError(
            f"Gmail API menolak pengiriman (HTTP {resp.status_code})."
        )

    return resp.json().get("id", "")
