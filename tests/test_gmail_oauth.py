"""
Alur "Hubungkan Gmail" (v2.1, Stage B2): terpisah dari login utama, meminta
scope sensitif gmail.send hanya saat admin menekan tombolnya, lalu menyimpan
refresh token TERENKRIPSI di User.
"""
from urllib.parse import parse_qs, urlparse

import pytest

from app.core.crypto import decrypt_secret
from app.core.oauth import GMAIL_SEND_SCOPE, GmailTokens
from app.core.security import create_oauth_state
from app.models.organization import User, UserRole
from app.routers.auth import GMAIL_STATE_COOKIE_NAME


def _get(client, url):
    return client.get(url, follow_redirects=False)


# --- authorize -------------------------------------------------------------

def test_authorize_butuh_login(client):
    r = _get(client, "/auth/gmail/authorize")
    assert r.status_code == 401


def test_authorize_redirect_ke_google_dengan_param_benar(client, make_user, login):
    login(make_user("admin@umbjm.ac.id"))
    r = _get(client, "/auth/gmail/authorize")
    assert r.status_code == 307
    loc = urlparse(r.headers["location"])
    q = parse_qs(loc.query)
    assert loc.netloc == "accounts.google.com"
    assert GMAIL_SEND_SCOPE in q["scope"][0].split()
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["include_granted_scopes"] == ["true"]
    assert GMAIL_STATE_COOKIE_NAME in r.headers.get("set-cookie", "")


# --- callback -------------------------------------------------------------

@pytest.fixture()
def connect_flow(client, monkeypatch, make_user, login):
    """User login + state cookie terpasang + exchange di-mock. Test tinggal
    mengatur email/scope/refresh_token yang 'dikembalikan Google'."""
    import app.routers.auth as auth_mod

    user = make_user("admin@umbjm.ac.id")
    login(user)

    box = {
        "email": "admin@umbjm.ac.id",
        "scope": f"openid email profile {GMAIL_SEND_SCOPE}",
        "refresh_token": "1//refresh-abc",
    }

    async def fake_exchange(code, redirect_uri):
        return GmailTokens(
            id_token="fake", refresh_token=box["refresh_token"], scope=box["scope"]
        )

    monkeypatch.setattr(auth_mod, "exchange_code_for_gmail_tokens", fake_exchange)
    monkeypatch.setattr(auth_mod, "verify_id_token", lambda _t: {"email": box["email"]})

    state = create_oauth_state()
    client.cookies.set(GMAIL_STATE_COOKIE_NAME, state)
    return {"box": box, "user": user, "url": f"/auth/gmail/callback?code=x&state={state}"}


def test_callback_state_tidak_cocok(client, connect_flow):
    r = _get(client, "/auth/gmail/callback?code=x&state=ngawur")
    assert r.headers["location"] == "/?gmail_error=expired"


def _reload(session, user):
    session.expire_all()
    return session.get(User, user.id)


def test_callback_sukses_menyimpan_token_terenkripsi(client, connect_flow, session):
    r = _get(client, connect_flow["url"])
    assert r.headers["location"] == "/?gmail=connected"

    row = _reload(session, connect_flow["user"])
    assert row.gmail_refresh_token_enc is not None
    assert row.gmail_refresh_token_enc != "1//refresh-abc"  # tersimpan terenkripsi
    assert decrypt_secret(row.gmail_refresh_token_enc) == "1//refresh-abc"
    assert row.gmail_connected_at is not None
    assert row.gmail_connected is True


def test_callback_akun_google_beda_ditolak(client, connect_flow, session):
    connect_flow["box"]["email"] = "orang.lain@umbjm.ac.id"
    r = _get(client, connect_flow["url"])
    assert r.headers["location"] == "/?gmail_error=wrong_account"
    assert _reload(session, connect_flow["user"]).gmail_refresh_token_enc is None


def test_callback_scope_kirim_tidak_disetujui(client, connect_flow, session):
    connect_flow["box"]["scope"] = "openid email profile"
    r = _get(client, connect_flow["url"])
    assert r.headers["location"] == "/?gmail_error=scope_declined"
    assert _reload(session, connect_flow["user"]).gmail_refresh_token_enc is None


def test_callback_tanpa_refresh_token_ditolak(client, connect_flow, session):
    connect_flow["box"]["refresh_token"] = None
    r = _get(client, connect_flow["url"])
    assert r.headers["location"] == "/?gmail_error=no_refresh_token"
    assert _reload(session, connect_flow["user"]).gmail_refresh_token_enc is None


# --- disconnect ----------------------------------------------------------

def test_disconnect_menghapus_token(client, monkeypatch, make_user, login, session):
    import app.routers.auth as auth_mod

    async def fake_revoke(token):
        fake_revoke.called = token

    fake_revoke.called = None
    monkeypatch.setattr(auth_mod, "revoke_token", fake_revoke)

    user = make_user("admin@umbjm.ac.id")
    from app.core.crypto import encrypt_secret

    user.gmail_refresh_token_enc = encrypt_secret("1//tok")
    session.add(user)
    session.commit()

    login(user)
    r = client.post("/auth/gmail/disconnect")
    assert r.status_code == 200
    assert r.json() == {"gmail_connected": False}

    session.expire_all()
    row = session.get(User, user.id)
    assert row.gmail_refresh_token_enc is None
    assert row.gmail_connected_at is None
    assert fake_revoke.called == "1//tok"  # revoke dipanggil dengan token asli


# --- /auth/me ------------------------------------------------------------

def test_me_mengekspos_gmail_connected(client, make_user, login):
    login(make_user("admin@umbjm.ac.id"))
    body = client.get("/auth/me").json()
    assert body["gmail_connected"] is False
    assert body["gmail_connected_at"] is None
