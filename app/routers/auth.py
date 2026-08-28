from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.core.database import get_session
from app.core.oauth import OAuthError, build_authorize_url, exchange_code_for_id_token, verify_id_token
from app.core.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    create_oauth_state,
    create_session_token,
    verify_oauth_state,
)
from app.dependencies import get_current_user
from app.models.organization import User, UserRole
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])

STATE_COOKIE_NAME = "oauth_state"


def _auth_error_redirect(code: str) -> RedirectResponse:
    """
    Alih-alih melempar HTTPException (yang muncul sebagai JSON mentah di tab
    browser karena /auth/callback adalah navigasi penuh, bukan fetch), kembali
    ke SPA dengan ?auth_error=<code>. auth.js yang menerjemahkan kode itu jadi
    pesan yang ramah di layar masuk lalu membersihkan query-nya.

    State cookie ikut dihapus supaya percobaan berikutnya mulai bersih.
    """
    response = RedirectResponse(f"/?auth_error={code}", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(STATE_COOKIE_NAME)
    return response


def _redirect_uri(request: Request) -> str:
    # Dibangun dari request, bukan dari config: supaya jalan apa adanya baik
    # di localhost (dev) maupun domain produksi tanpa perlu env terpisah,
    # selama URI-nya sudah didaftarkan sebagai authorized redirect URI di
    # Google Cloud Console.
    return str(request.url_for("auth_callback"))


@router.get("/login")
def login(request: Request):
    state = create_oauth_state()
    authorize_url = build_authorize_url(_redirect_uri(request), state)

    response = RedirectResponse(authorize_url)
    response.set_cookie(
        STATE_COOKIE_NAME,
        state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return response


@router.get("/callback", name="auth_callback")
async def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: Session = Depends(get_session),
):
    if error:
        # Pengguna membatalkan di layar consent Google, atau kasus serupa.
        return _auth_error_redirect("cancelled")

    cookie_state = request.cookies.get(STATE_COOKIE_NAME)
    if not state or not cookie_state or state != cookie_state or not verify_oauth_state(state):
        # Cocokkan DUA arah: token harus valid tanda tangannya (verify_oauth_state)
        # DAN harus sama persis dengan yang kita taruh di cookie saat /login.
        # Ini yang mencegah CSRF pada alur OAuth.
        return _auth_error_redirect("expired")

    if not code:
        return _auth_error_redirect("expired")

    try:
        raw_id_token = await exchange_code_for_id_token(code, _redirect_uri(request))
        claims = verify_id_token(raw_id_token)
    except OAuthError:
        # Termasuk email di luar domain @umbjm.ac.id dan email belum terverifikasi.
        return _auth_error_redirect("oauth")

    email = claims["email"].lower()
    name = claims.get("name")
    picture_url = claims.get("picture")

    user = session.exec(select(User).where(User.email == email)).first()

    if user is None:
        if email in settings.superadmin_email_list:
            # Bootstrap: superadmin pertama tidak perlu baris User yang
            # dibuat manual lebih dulu, supaya tidak ada masalah ayam-telur
            # (siapa yang mengundang superadmin pertama?). Superadmin
            # berikutnya di luar daftar env ini tetap harus diundang oleh
            # superadmin yang sudah ada, lewat UI di Stage 4.
            user = User(email=email, role=UserRole.superadmin, unit_id=None)
            session.add(user)
        else:
            # Login = daftar undangan, bukan pendaftaran terbuka. Punya email
            # @umbjm.ac.id saja tidak cukup (mahasiswa pun punya).
            return _auth_error_redirect("not_invited")

    if not user.is_active:
        # Aksesnya sudah dicabut superadmin. Ditolak DI SINI (sebelum cookie
        # sesi dipasang) supaya tidak ada sesi setengah jadi yang tiap request
        # kena 401 tanpa penjelasan — get_current_user juga tetap menolaknya
        # sebagai lapis kedua.
        return _auth_error_redirect("deactivated")

    user.name = name
    user.picture_url = picture_url
    user.last_login_at = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)

    if user.id is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Gagal menyimpan sesi login.")

    response = RedirectResponse("/")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        create_session_token(user.id),
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    response.delete_cookie(STATE_COOKIE_NAME)
    return response


@router.post("/logout")
def logout():
    response = RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "email": user.email,
        "name": user.name,
        "picture_url": user.picture_url,
        "role": user.role.value,
        "unit_id": user.unit_id,
        # Nama unit ikut dikirim supaya topbar bisa menampilkan "Admin ·
        # Fakultas Farmasi" tanpa frontend perlu memanggil /admin/units
        # terpisah. Null untuk superadmin yang tidak terikat satu unit.
        "unit_name": user.unit.name if user.unit else None,
    }