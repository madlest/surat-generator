"""
Dependency otorisasi. Ditulis di Stage 2 supaya /auth/me bisa diuji, tapi
belum dipasang ke endpoint admin.py/generate.py yang sudah ada — itu baru
terjadi di Stage 3, sengaja dipisah supaya tiap tahap bisa direview terpisah.
"""
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session

from app.core.database import get_session
from app.core.security import SESSION_COOKIE_NAME, read_session_token
from app.models.organization import User, UserRole


def get_current_user(
    request: Request,
    session: Session = Depends(get_session),
) -> User:
    """
    Mengambil User dari cookie sesi. Melempar 401 kalau cookie tidak ada,
    signature-nya tidak valid, kedaluwarsa, user-nya sudah dihapus dari DB,
    atau is_active sudah dimatikan (jalur pencabutan akses instan tanpa
    perlu tabel session — lihat catatan di app/core/security.py).
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Belum login")

    user_id = read_session_token(token)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesi tidak valid atau kedaluwarsa")

    user = session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Akun tidak ditemukan atau dinonaktifkan")

    return user


def scope_unit_id(user: User) -> int | None:
    """
    Mengembalikan unit_id yang harus dipakai untuk membatasi query, atau None
    kalau user boleh melihat lintas semua unit.

    Dipusatkan di sini (bukan diulang `if user.role == UserRole.admin` di
    setiap endpoint) supaya kalau nanti ada role ketiga (mis. "auditor" yang
    disebut di percakapan kita — lihat catatan roadmap), cukup diubah di satu
    tempat.
    """
    if user.role == UserRole.superadmin:
        return None
    return user.unit_id