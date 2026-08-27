"""
Session cookie stateless (ditandatangani, bukan dienkripsi) pakai itsdangerous.

Kenapa stateless (bukan tabel session di DB): skala pengguna proyek ini kecil
(segelintir admin per unit), jadi query tambahan + housekeeping baris
kedaluwarsa tidak sepadan manfaatnya. Pencabutan akses tetap bisa instan lewat
`User.is_active = False`, yang dicek ulang di setiap request oleh
`app/dependencies.py` — jadi cookie lama otomatis tidak berlaku begitu
is_active dimatikan, walau signature-nya sendiri masih valid.
"""
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import settings

SESSION_COOKIE_NAME = "session"
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7  # 7 hari

# State OAuth berumur pendek: hanya perlu hidup selama proses redirect ke
# Google dan kembali, bukan selama sesi login.
STATE_MAX_AGE_SECONDS = 60 * 10  # 10 menit


def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret_key, salt="surat-generator-session")


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret_key, salt="surat-generator-oauth-state")


def create_session_token(user_id: int) -> str:
    return _session_serializer().dumps({"uid": user_id})


def read_session_token(token: str) -> int | None:
    """Mengembalikan user_id kalau signature dan umur token valid, selain itu None."""
    try:
        data = _session_serializer().loads(token, max_age=SESSION_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    return uid if isinstance(uid, int) else None


def create_oauth_state() -> str:
    """
    Token acak+bertanda tangan untuk mencocokkan redirect /auth/login dengan
    /auth/callback, mencegah serangan CSRF pada alur OAuth (penyerang memaksa
    korban login dengan authorization code milik penyerang).
    """
    import secrets

    return _state_serializer().dumps({"nonce": secrets.token_urlsafe(16)})


def verify_oauth_state(token: str) -> bool:
    try:
        _state_serializer().loads(token, max_age=STATE_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return False
    return True