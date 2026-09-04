"""
Enkripsi simetris untuk rahasia kecil yang harus tersimpan di DB dalam bentuk
terenkripsi — sekarang cuma refresh token Gmail per-admin (fitur "Hubungkan
Gmail" v2.1).

Fernet (AES-128-CBC + HMAC-SHA256, dari `cryptography`) dipilih karena API-nya
sempit dan susah dipakai salah: satu kunci, `encrypt`/`decrypt`, ciphertext
sudah ber-authentication tag dan timestamp. Kunci diambil dari
`settings.email_token_key` (lihat config.py) dan TIDAK di-cache di level modul
supaya test bisa mengganti kunci lewat monkeypatch.
"""
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


class SecretCryptoError(RuntimeError):
    """Kunci belum diset, kunci tidak valid, atau ciphertext tidak bisa
    didekripsi (kunci berubah / data rusak). Dibedakan dari error lain supaya
    pemanggil bisa menampilkan "hubungkan ulang Gmail" alih-alih 500 mentah."""


def _fernet() -> Fernet:
    key = settings.email_token_key
    if not key:
        raise SecretCryptoError(
            "EMAIL_TOKEN_KEY belum diisi di .env. Bikin dengan: "
            'python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    try:
        return Fernet(key)
    except (ValueError, TypeError) as exc:
        raise SecretCryptoError(f"EMAIL_TOKEN_KEY bukan kunci Fernet yang valid: {exc}") from exc


def encrypt_secret(plaintext: str) -> str:
    """String biasa -> token terenkripsi (str, aman disimpan di kolom teks)."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    """Kebalikan encrypt_secret. Melempar SecretCryptoError kalau token tidak
    cocok dengan kunci sekarang."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise SecretCryptoError(
            "Token terenkripsi tidak bisa didekripsi — EMAIL_TOKEN_KEY berubah "
            "atau data rusak."
        ) from exc
