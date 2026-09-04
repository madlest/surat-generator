"""
Fixture bersama untuk test.

Ganjalan utama: router (superadmin.py, admin.py, generate.py) memakai `engine`
module-level lewat `with Session(engine)`, bukan `Depends(get_session)`. Jadi
sekadar meng-override dependency tidak cukup — `engine` di tiap modul itu harus
di-monkeypatch ke engine SQLite in-memory milik test.

Login disimulasikan dengan mencetak cookie sesi ASLI (create_session_token),
supaya rantai require_superadmin -> get_current_user benar-benar dieksekusi,
bukan di-mock.
"""
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool

import app.core.database as database_module

# Impor eksplisit supaya semua tabel terdaftar di SQLModel.metadata sebelum
# create_all dipanggil (letter_type mengimpor organization, bukan sebaliknya).
import app.models.letter_type  # noqa: F401
from app.core.security import SESSION_COOKIE_NAME, create_session_token
from app.models.organization import User, UserRole


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # satu koneksi dibagi ke semua Session -> data konsisten
    )
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture(autouse=True)
def _email_token_key(monkeypatch):
    """Kunci Fernet sungguhan (acak per test) supaya app/core/crypto.py bisa
    dipakai tanpa .env. Di-set di instance settings, bukan env var, karena
    settings sudah ter-load saat test mulai."""
    from cryptography.fernet import Fernet

    from app.core.config import settings as app_settings

    monkeypatch.setattr(app_settings, "email_token_key", Fernet.generate_key().decode())


@pytest.fixture(autouse=True)
def _patch_engine(engine, monkeypatch):
    monkeypatch.setattr(database_module, "engine", engine)
    import app.routers.admin as admin_module
    import app.routers.generate as generate_module
    import app.routers.superadmin as superadmin_module

    monkeypatch.setattr(admin_module, "engine", engine)
    monkeypatch.setattr(generate_module, "engine", engine)
    monkeypatch.setattr(superadmin_module, "engine", engine)


@pytest.fixture()
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture()
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def make_user(session):
    def _make(email, role=UserRole.admin, unit_id=None, is_active=True):
        user = User(email=email, role=role, unit_id=unit_id, is_active=is_active)
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    return _make


@pytest.fixture()
def login(client):
    """Pasang cookie sesi untuk user tertentu di TestClient."""

    def _login(user):
        client.cookies.set(SESSION_COOKIE_NAME, create_session_token(user.id))
        return client

    return _login
