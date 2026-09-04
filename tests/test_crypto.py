"""app/core/crypto.py — enkripsi refresh token Gmail sebelum masuk DB."""
import pytest
from cryptography.fernet import Fernet

from app.core.config import settings
from app.core.crypto import SecretCryptoError, decrypt_secret, encrypt_secret


def test_roundtrip():
    plain = "1//0abcDEF-refresh-token-xyz_123"
    assert decrypt_secret(encrypt_secret(plain)) == plain


def test_ciphertext_is_not_plaintext_and_nondeterministic():
    plain = "rahasia"
    a = encrypt_secret(plain)
    b = encrypt_secret(plain)
    assert plain not in a
    assert a != b  # Fernet menyisipkan IV acak + timestamp
    assert decrypt_secret(a) == decrypt_secret(b) == plain


def test_unicode_survives():
    plain = "tökén—dengan–ünïcode ✉"
    assert decrypt_secret(encrypt_secret(plain)) == plain


def test_decrypt_with_different_key_fails(monkeypatch):
    token = encrypt_secret("x")
    monkeypatch.setattr(settings, "email_token_key", Fernet.generate_key().decode())
    with pytest.raises(SecretCryptoError):
        decrypt_secret(token)


def test_garbage_token_fails():
    with pytest.raises(SecretCryptoError):
        decrypt_secret("bukan-token-fernet")


def test_missing_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "email_token_key", "")
    with pytest.raises(SecretCryptoError, match="EMAIL_TOKEN_KEY"):
        encrypt_secret("x")


def test_invalid_key_raises(monkeypatch):
    monkeypatch.setattr(settings, "email_token_key", "terlalu-pendek")
    with pytest.raises(SecretCryptoError):
        encrypt_secret("x")
