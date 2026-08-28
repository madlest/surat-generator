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
import httpx
from urllib.parse import urlencode

from google.auth import exceptions as google_auth_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from app.core.config import settings

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

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


async def exchange_code_for_id_token(code: str, redirect_uri: str) -> str:
    """Menukar authorization code dengan token dari Google, mengembalikan
    ID token (JWT) mentah yang belum diverifikasi."""
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

    body = resp.json()
    raw_id_token = body.get("id_token")
    if not raw_id_token:
        raise OAuthError("Respons token dari Google tidak berisi id_token")
    return raw_id_token


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