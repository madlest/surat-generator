"""Test /auth/me — fokus pada field unit_name yang dipakai topbar frontend."""
from app.models.organization import Unit, UserRole


def test_me_tanpa_login_401(client):
    assert client.get("/auth/me").status_code == 401


def test_me_admin_menyertakan_unit_name(client, login, session, make_user):
    unit = Unit(slug="farmasi", name="Fakultas Farmasi")
    session.add(unit)
    session.commit()
    session.refresh(unit)

    admin = make_user("admin@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id)
    login(admin)

    body = client.get("/auth/me").json()
    assert body["role"] == "admin"
    assert body["unit_id"] == unit.id
    assert body["unit_name"] == "Fakultas Farmasi"


def test_me_superadmin_unit_name_null(client, login, make_user):
    login(make_user("super@umbjm.ac.id", role=UserRole.superadmin))

    body = client.get("/auth/me").json()
    assert body["role"] == "superadmin"
    assert body["unit_id"] is None
    assert body["unit_name"] is None
