"""
Test /auth/callback: kegagalan login sekarang REDIRECT balik ke SPA dengan
?auth_error=<code>, bukan melempar JSON 4xx mentah di tab browser.
"""
import pytest

from app.core.security import create_oauth_state
from app.models.organization import UserRole
from app.routers.auth import STATE_COOKIE_NAME


def _get(client, url):
    return client.get(url, follow_redirects=False)


# --- jalur yang berhenti lebih awal (tanpa panggil Google) ---------------

def test_user_batal_di_google_redirect_cancelled(client):
    r = _get(client, "/auth/callback?error=access_denied")
    assert r.status_code == 303
    assert r.headers["location"] == "/?auth_error=cancelled"


def test_state_tidak_cocok_redirect_expired(client):
    r = _get(client, "/auth/callback?code=abc&state=ngasal")
    assert r.status_code == 303
    assert r.headers["location"] == "/?auth_error=expired"


# --- jalur yang butuh mock token Google --------------------------------

@pytest.fixture()
def fake_google(client, monkeypatch):
    """Lewati pertukaran code->token; kembalikan email yang bisa diatur per test."""
    import app.routers.auth as auth_mod

    claims = {"email": "orang@umbjm.ac.id", "name": "Orang Baru", "picture": None}

    async def fake_exchange(code, redirect_uri):
        return "fake-id-token"

    monkeypatch.setattr(auth_mod, "exchange_code_for_id_token", fake_exchange)
    monkeypatch.setattr(auth_mod, "verify_id_token", lambda _token: claims)

    state = create_oauth_state()
    client.cookies.set(STATE_COOKIE_NAME, state)
    return {"claims": claims, "url": f"/auth/callback?code=abc&state={state}"}


def test_email_belum_diundang_redirect_not_invited(client, fake_google):
    fake_google["claims"]["email"] = "belum-diundang@umbjm.ac.id"
    r = _get(client, fake_google["url"])
    assert r.status_code == 303
    assert r.headers["location"] == "/?auth_error=not_invited"


def test_user_terdaftar_berhasil_login(client, fake_google, make_user):
    make_user("orang@umbjm.ac.id", role=UserRole.superadmin)
    r = _get(client, fake_google["url"])
    assert r.headers["location"] == "/"
    assert "session=" in r.headers.get("set-cookie", "")


def test_user_dinonaktifkan_redirect_deactivated_tanpa_sesi(client, fake_google, make_user):
    make_user("orang@umbjm.ac.id", role=UserRole.admin, unit_id=None, is_active=False)
    r = _get(client, fake_google["url"])
    assert r.status_code == 303
    assert r.headers["location"] == "/?auth_error=deactivated"
    # Tidak ada cookie sesi yang dipasang untuk akun nonaktif.
    assert "session=" not in r.headers.get("set-cookie", "")
