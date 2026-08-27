"""
Endpoint khusus superadmin: mengelola daftar unit dan mengundang/mencabut
akses admin.

Semua endpoint di sini memakai require_superadmin, bukan get_current_user
biasa — admin biasa sama sekali tidak boleh melihat atau menyentuh endpoint
ini, beda dengan admin.py (jenis surat) yang admin biasa juga boleh pakai,
di-scope ke unitnya sendiri.
"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, col, select

from app.core.database import engine
from app.core.oauth import ALLOWED_EMAIL_DOMAIN
from app.dependencies import require_superadmin
from app.models.organization import Unit, User, UserRole
from app.routers.admin import MAX_SLUG_LENGTH, SLUG_PATTERN

router = APIRouter(prefix="/admin", tags=["Admin - Superadmin"])


class CreateUnitRequest(BaseModel):
    slug: str
    name: str


class InviteUserRequest(BaseModel):
    email: str
    role: UserRole = UserRole.admin
    unit_id: int | None = None


def _validate_unit_slug(raw_slug: str) -> str:
    # Regex dan batas panjang yang SAMA dengan slug jenis surat (diimpor dari
    # admin.py, bukan didefinisikan ulang) karena unit_slug juga dipakai
    # sebagai nama folder di disk (app/templates/uploaded/{unit_slug}/),
    # persis seperti slug jenis surat dipakai sebagai nama file.
    cleaned = raw_slug.strip().lower()
    if len(cleaned) > MAX_SLUG_LENGTH or not SLUG_PATTERN.match(cleaned):
        raise HTTPException(
            status_code=400,
            detail=(
                "Slug unit hanya boleh berisi huruf kecil, angka, dan tanda hubung "
                f"(maksimal {MAX_SLUG_LENGTH} karakter). Contoh: fakultas-hukum."
            ),
        )
    return cleaned


@router.get("/units")
def list_units(_: User = Depends(require_superadmin)):
    with Session(engine) as session:
        return session.exec(select(Unit).order_by(col(Unit.name))).all()


@router.post("/units")
def create_unit(payload: CreateUnitRequest, _: User = Depends(require_superadmin)):
    slug = _validate_unit_slug(payload.slug)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nama unit wajib diisi.")

    with Session(engine) as session:
        existing = session.exec(select(Unit).where(Unit.slug == slug)).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Slug unit '{slug}' sudah dipakai.")

        unit = Unit(slug=slug, name=name)
        session.add(unit)
        session.commit()
        session.refresh(unit)
        return {"id": unit.id, "slug": unit.slug, "name": unit.name}


@router.get("/users")
def list_users(_: User = Depends(require_superadmin)):
    with Session(engine) as session:
        users = session.exec(select(User).order_by(col(User.email))).all()
        return [
            {
                "id": u.id,
                "email": u.email,
                "name": u.name,
                "role": u.role.value,
                "unit_id": u.unit_id,
                "unit_name": u.unit.name if u.unit else None,
                "is_active": u.is_active,
                "last_login_at": u.last_login_at,
            }
            for u in users
        ]


@router.post("/users/invite")
def invite_user(payload: InviteUserRequest, _: User = Depends(require_superadmin)):
    """
    Membuat baris User untuk email yang belum pernah login — inti dari model
    "diundang dulu, baru bisa login" yang jadi dasar seluruh sistem otorisasi
    ini. name/picture_url/last_login_at sengaja dibiarkan kosong, baru terisi
    otomatis saat orangnya login pertama kali lewat Google (lihat auth.py).
    """
    email = payload.email.strip().lower()
    if not email.endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        raise HTTPException(status_code=400, detail=f"Email harus berdomain @{ALLOWED_EMAIL_DOMAIN}.")

    if payload.role == UserRole.admin and payload.unit_id is None:
        raise HTTPException(status_code=400, detail="unit_id wajib diisi untuk mengundang admin biasa.")
    if payload.role == UserRole.superadmin and payload.unit_id is not None:
        raise HTTPException(
            status_code=400,
            detail="unit_id harus kosong untuk mengundang superadmin (tidak terikat satu unit).",
        )

    with Session(engine) as session:
        existing = session.exec(select(User).where(User.email == email)).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Email '{email}' sudah pernah diundang / terdaftar.")

        if payload.unit_id is not None:
            unit = session.get(Unit, payload.unit_id)
            if unit is None:
                raise HTTPException(status_code=400, detail=f"Unit dengan id {payload.unit_id} tidak ditemukan.")

        user = User(email=email, role=payload.role, unit_id=payload.unit_id)
        session.add(user)
        session.commit()
        session.refresh(user)
        return {"id": user.id, "email": user.email, "role": user.role.value, "unit_id": user.unit_id}


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, _: User = Depends(require_superadmin)):
    """
    Mencabut akses tanpa menghapus barisnya (lihat User.is_active). Menolak
    kalau target adalah SATU-SATUNYA superadmin yang masih aktif — kalau
    dibolehkan, sistem kehilangan akses admin sepenuhnya karena tidak ada
    lagi siapa pun yang bisa mengundang superadmin baru lewat UI (satu-
    satunya jalan tersisa adalah mengedit database secara manual).
    """
    with Session(engine) as session:
        target = session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User tidak ditemukan.")

        if target.role == UserRole.superadmin:
            active_superadmin_count = len(
                session.exec(
                    select(User).where(User.role == UserRole.superadmin, col(User.is_active).is_(True))
                ).all()
            )
            if active_superadmin_count <= 1:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Tidak bisa menonaktifkan satu-satunya superadmin yang aktif — "
                        "sistem akan kehilangan akses admin sepenuhnya."
                    ),
                )

        target.is_active = False
        session.add(target)
        session.commit()
        return {"id": target.id, "is_active": False}


@router.patch("/users/{user_id}/reactivate")
def reactivate_user(user_id: int, _: User = Depends(require_superadmin)):
    with Session(engine) as session:
        target = session.get(User, user_id)
        if target is None:
            raise HTTPException(status_code=404, detail="User tidak ditemukan.")

        target.is_active = True
        session.add(target)
        session.commit()
        return {"id": target.id, "is_active": True}
