"""
Fungsi murni untuk alur OAuth 2.0 Google, dipisah dari router supaya gampang
diuji tanpa perlu request HTTP sungguhan.

Catatan penting (lihat memori proyek / keputusan v2.0.0): consent screen
bertipe "External", bukan "Internal", karena akses Google Cloud Platform
dinonaktifkan admin Workspace kampus untuk akun @umbjm.ac.id. Konsekuensinya
Google TIDAK membatasi login ke domain kampus secara otomatis — pembatasan
itu kita lakukan sendiri di verify_id_token() di bawah ini. Ini satu-satunya
penjaga; jangan dilonggarkan tanpa pertimbangan ulang.
"""
from typing import NamedTuple
from urllib.parse import urlencode

import httpx

from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

# Scope pengiriman email (v2.1). Sensitif — hanya diminta lewat alur
# "Hubungkan Gmail" yang terpisah dari login utama, saat admin memang menekan
# tombolnya. OAUTH_SCOPES di atas (login utama) sengaja TIDAK memuat ini
# supaya admin yang tak pernah kirim surat tidak kena consent screen sensitif.
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_OAUTH_SCOPES = ("openid", "email", "profile", GMAIL_SEND_SCOPE)

# Domain kampus. Ditulis sebagai konstanta (bukan config) karena ini aturan
# bisnis yang tidak dimaksudkan untuk gampang diubah lewat .env — mengubahnya
# adalah keputusan yang harus sengaja disadari, bukan salah ketik di env file.
ALLOWED_EMAIL_DOMAIN = "umbjm.ac.id"

# Scope sengaja minimal: hanya identitas dasar. Tidak ada scope Drive/Gmail/
# dsb, supaya app tetap tergolong non-sensitif dan tidak memicu proses
# verifikasi Google walau nanti dipublish dari status Testing.
OAUTH_SCOPES = ("openid", "email", "profile")


class OAuthError(Exception):
    """Kegagalan pada tahap manapun di alur OAuth: penolakan yang disengaja
    (domain salah, akun belum diundang) maupun kegagalan teknis (signature
    tidak valid). Router menerjemahkan ini jadi respons HTTP yang sesuai."""


def build_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(OAUTH_SCOPES),
        "state": state,
        # "select_account" supaya orang yang punya beberapa akun Google tidak
        # diam-diam terus login pakai akun yang sedang aktif di browsernya.
        "prompt": "select_account",
    }
    query = urlencode(params)
    return f"{GOOGLE_AUTH_ENDPOINT}?{query}"


async def _exchange_code(code: str, redirect_uri: str) -> dict:
    """Menukar authorization code dengan token dari Google. Mengembalikan body
    respons mentah (id_token, dan — kalau diminta — access_token/refresh_token/
    scope). Dipakai bersama oleh alur login utama dan alur "Hubungkan Gmail"."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                GOOGLE_TOKEN_ENDPOINT,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
        except httpx.HTTPError as exc:
            raise OAuthError(f"Gagal menghubungi Google: {exc}") from exc

    if resp.status_code != 200:
        raise OAuthError(f"Google menolak penukaran code (HTTP {resp.status_code}): {resp.text}")

    return resp.json()


async def exchange_code_for_id_token(code: str, redirect_uri: str) -> str:
    """Alur login utama: cukup ID token (JWT) mentah yang belum diverifikasi."""
    body = await _exchange_code(code, redirect_uri)
    raw_id_token = body.get("id_token")
    if not raw_id_token:
        raise OAuthError("Respons token dari Google tidak berisi id_token")
    return raw_id_token


class GmailTokens(NamedTuple):
    id_token: str          # untuk memverifikasi identitas yang meng-consent
    refresh_token: str | None  # None kalau Google tak mengembalikannya
    scope: str             # daftar scope yang BENAR-BENAR diberikan, dipisah spasi


async def exchange_code_for_gmail_tokens(code: str, redirect_uri: str) -> GmailTokens:
    """Alur "Hubungkan Gmail": butuh refresh token (disimpan terenkripsi) dan
    daftar scope yang benar-benar disetujui user (dia bisa mencentang-lepas
    izin kirim email di layar consent)."""
    body = await _exchange_code(code, redirect_uri)
    raw_id_token = body.get("id_token")
    if not raw_id_token:
        raise OAuthError("Respons token dari Google tidak berisi id_token")
    return GmailTokens(
        id_token=raw_id_token,
        refresh_token=body.get("refresh_token"),
        scope=body.get("scope", ""),
    )


async def revoke_token(token: str) -> None:
    """Best-effort: minta Google mencabut refresh token saat admin menekan
    "Putuskan Gmail". Kegagalan diabaikan (token mungkin sudah kedaluwarsa /
    dicabut manual) — pemanggil tetap menghapus token dari DB."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(GOOGLE_REVOKE_ENDPOINT, data={"token": token})
    except httpx.HTTPError:
        pass


def build_gmail_authorize_url(redirect_uri: str, state: str) -> str:
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(GMAIL_OAUTH_SCOPES),
        "state": state,
        # offline + prompt=consent = jaminan dapat refresh token baru tiap kali
        # admin menjalankan alur ini (tanpa consent, Google hanya mengirim
        # refresh token pada persetujuan PERTAMA saja).
        "access_type": "offline",
        "prompt": "consent",
        # Supaya token tetap membawa scope identitas yang sudah disetujui di
        # login utama, bukan menggantinya.
        "include_granted_scopes": "true",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


def verify_id_token(raw_id_token: str) -> dict:
    """
    Memverifikasi signature, issuer, dan audience ID token terhadap kunci
    publik Google (JWKS, diambil & di-cache otomatis oleh library), lalu
    menegakkan aturan bisnis kita: email terverifikasi dan berdomain kampus.

    Mengembalikan claims (dict) kalau valid. Melempar OAuthError kalau tidak.
    """
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), settings.google_client_id
        )
    except ValueError as exc:
        # google-auth melempar ValueError generik untuk segala jenis token
        # tidak valid: signature salah, kedaluwarsa, aud tidak cocok, dst.
        raise OAuthError(f"ID token tidak valid: {exc}") from exc
    except google_auth_exceptions.GoogleAuthError as exc:
        # Mencakup TransportError: gagal mengambil kunci publik (JWKS) dari
        # Google, misal karena API mereka sedang bermasalah atau jaringan
        # server kita terputus. Kegagalan operasional, bukan token yang
        # invalid — tapi tetap harus gagal login dengan aman, bukan crash
        # dengan 500 mentah ke pengguna.
        raise OAuthError(f"Gagal memverifikasi token ke Google: {exc}") from exc

    if not claims.get("email_verified", False):
        raise OAuthError("Email belum diverifikasi oleh Google")

    email = claims.get("email", "")
    if not email.lower().endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        raise OAuthError(f"Email harus berdomain @{ALLOWED_EMAIL_DOMAIN}")

    # verify_oauth2_token mengembalikan Mapping[str, Any], bukan dict secara
    # tegas menurut stub google-auth — dikonversi eksplisit di sini supaya
    # cocok dengan anotasi return type fungsi ini.
    return dict(claims)