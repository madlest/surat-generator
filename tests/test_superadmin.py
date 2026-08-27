"""
Test endpoint superadmin (app/routers/superadmin.py).

Fokus: otorisasi lintas-role (admin biasa dilarang total, bukan sekadar
di-scope), validasi input, dan pengaman "jangan sampai kehilangan superadmin
terakhir".
"""
import pytest

from app.models.organization import Unit, UserRole

SUPERADMIN_PATHS = [
    ("get", "/admin/units"),
    ("post", "/admin/units"),
    ("get", "/admin/users"),
    ("post", "/admin/users/invite"),
    ("patch", "/admin/users/1/deactivate"),
    ("patch", "/admin/users/1/reactivate"),
]


@pytest.fixture()
def unit(session):
    u = Unit(slug="farmasi", name="Fakultas Farmasi")
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture()
def superadmin(make_user):
    return make_user("super@umbjm.ac.id", role=UserRole.superadmin)


@pytest.fixture()
def admin(make_user, unit):
    return make_user("admin@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id)


# --- Otorisasi -------------------------------------------------------------

def _call(client, method, path):
    kwargs = {} if method == "get" else {"json": {}}
    return getattr(client, method)(path, **kwargs)


@pytest.mark.parametrize("method,path", SUPERADMIN_PATHS)
def test_tanpa_login_ditolak_401(client, method, path):
    assert _call(client, method, path).status_code == 401


@pytest.mark.parametrize("method,path", SUPERADMIN_PATHS)
def test_admin_biasa_ditolak_403(client, login, admin, method, path):
    login(admin)
    assert _call(client, method, path).status_code == 403


def test_user_nonaktif_ditolak_401(client, login, make_user):
    dead = make_user("mati@umbjm.ac.id", role=UserRole.superadmin, is_active=False)
    login(dead)
    assert client.get("/admin/units").status_code == 401


# --- Unit ----------------------------------------------------------------

def test_superadmin_bisa_buat_dan_lihat_unit(client, login, superadmin):
    login(superadmin)
    resp = client.post("/admin/units", json={"slug": "hukum", "name": "Fakultas Hukum"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["slug"] == "hukum"

    listing = client.get("/admin/units").json()
    assert [u["slug"] for u in listing] == ["hukum"]


def test_slug_unit_tidak_valid_ditolak(client, login, superadmin):
    login(superadmin)
    resp = client.post("/admin/units", json={"slug": "Fakultas Hukum!", "name": "X"})
    assert resp.status_code == 400


def test_slug_unit_dinormalisasi_dan_duplikat_ditolak(client, login, superadmin):
    login(superadmin)
    assert client.post("/admin/units", json={"slug": "  HUKUM  ", "name": "Fakultas Hukum"}).status_code == 200
    dup = client.post("/admin/units", json={"slug": "hukum", "name": "Lain"})
    assert dup.status_code == 400


def test_nama_unit_kosong_ditolak(client, login, superadmin):
    login(superadmin)
    assert client.post("/admin/units", json={"slug": "hukum", "name": "   "}).status_code == 400


# --- Undang user -------------------------------------------------------------

def test_undang_admin_butuh_unit_id(client, login, superadmin):
    login(superadmin)
    resp = client.post("/admin/users/invite", json={"email": "baru@umbjm.ac.id"})
    assert resp.status_code == 400


def test_undang_superadmin_tidak_boleh_ada_unit_id(client, login, superadmin, unit):
    login(superadmin)
    resp = client.post(
        "/admin/users/invite",
        json={"email": "baru@umbjm.ac.id", "role": "superadmin", "unit_id": unit.id},
    )
    assert resp.status_code == 400


def test_undang_admin_sukses_lalu_duplikat_ditolak(client, login, superadmin, unit):
    login(superadmin)
    ok = client.post(
        "/admin/users/invite",
        json={"email": "Baru@umbjm.ac.id", "role": "admin", "unit_id": unit.id},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["email"] == "baru@umbjm.ac.id"

    users = client.get("/admin/users").json()
    invited = next(u for u in users if u["email"] == "baru@umbjm.ac.id")
    assert invited["name"] is None and invited["last_login_at"] is None

    dup = client.post(
        "/admin/users/invite",
        json={"email": "baru@umbjm.ac.id", "role": "admin", "unit_id": unit.id},
    )
    assert dup.status_code == 400


def test_undang_superadmin_tanpa_unit_id_sukses(client, login, superadmin):
    login(superadmin)
    resp = client.post(
        "/admin/users/invite",
        json={"email": "super3@umbjm.ac.id", "role": "superadmin"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["unit_id"] is None


def test_undang_email_domain_salah_ditolak(client, login, superadmin, unit):
    login(superadmin)
    resp = client.post(
        "/admin/users/invite",
        json={"email": "orang@gmail.com", "role": "admin", "unit_id": unit.id},
    )
    assert resp.status_code == 400


def test_undang_admin_unit_tidak_ada_ditolak(client, login, superadmin):
    login(superadmin)
    resp = client.post(
        "/admin/users/invite",
        json={"email": "baru@umbjm.ac.id", "role": "admin", "unit_id": 999},
    )
    assert resp.status_code == 400


# --- Deactivate / reactivate ------------------------------------------------

def test_tidak_bisa_nonaktifkan_satu_satunya_superadmin(client, login, superadmin):
    login(superadmin)
    resp = client.patch(f"/admin/users/{superadmin.id}/deactivate")
    assert resp.status_code == 400


def test_bisa_nonaktifkan_superadmin_kalau_masih_ada_yang_lain(client, login, superadmin, make_user):
    other = make_user("super2@umbjm.ac.id", role=UserRole.superadmin)
    login(superadmin)

    assert client.patch(f"/admin/users/{other.id}/deactivate").status_code == 200
    # sekarang tinggal satu superadmin aktif lagi
    assert client.patch(f"/admin/users/{superadmin.id}/deactivate").status_code == 400
    # reactivate yang tadi
    assert client.patch(f"/admin/users/{other.id}/reactivate").status_code == 200


def test_nonaktifkan_admin_biasa_lalu_reactivate(client, login, superadmin, admin):
    login(superadmin)
    assert client.patch(f"/admin/users/{admin.id}/deactivate").json()["is_active"] is False
    assert client.patch(f"/admin/users/{admin.id}/reactivate").json()["is_active"] is True


def test_deactivate_user_tidak_ada_404(client, login, superadmin):
    login(superadmin)
    assert client.patch("/admin/users/12345/deactivate").status_code == 404
