"""
Endpoint Stage B4: POST /generate/jobs/{job_id}/send-email,
GET /generate/send-batches/{id}/status, POST .../retry.
"""
import pytest
from sqlmodel import select

from app.core.crypto import encrypt_secret
from app.core.job_store import job_store
from app.models.delivery import Delivery, DeliveryStatus
from app.models.organization import Unit, User, UserRole
from app.services import delivery as delivery_mod


@pytest.fixture(autouse=True)
def _clear_jobs():
    job_store._jobs.clear()
    yield
    job_store._jobs.clear()


@pytest.fixture()
def unit(session):
    u = Unit(slug="farmasi", name="Fakultas Farmasi")
    session.add(u)
    session.commit()
    session.refresh(u)
    return u


@pytest.fixture()
def admin_gmail(session, unit):
    user = User(
        email="admin@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id,
        gmail_refresh_token_enc=encrypt_secret("1//refresh"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def done_job(unit, tmp_path):
    """Job selesai + send_context email-enabled + 2 PDF di disk (2 penerima,
    salah satunya berbagi email dengan yang lain)."""
    p1, p2, p3 = (tmp_path / f"s{i}.pdf" for i in range(3))
    for p in (p1, p2, p3):
        p.write_bytes(b"%PDF-1.4 x")
    job_id = "job-abc"
    job_store.create_job(job_id=job_id, total=3, unit_id=unit.id)
    job_store.mark_done(job_id, str(tmp_path / "hasil.zip"))
    job_store.attach_send_context(job_id, {
        "letter_type_id": 1,
        "unit_id": unit.id,
        "send_email_enabled": True,
        "email_subject_template": "Surat untuk {nama}",
        "email_body_template": "Halo {nama}",
        "email_field_key": "email",
        "recipients": [
            {"index": 1, "label": "Budi", "pdf_path": str(p1),
             "recipient_values": {"nama": "Budi", "email": "budi@x.com"}},
            {"index": 2, "label": "Sri", "pdf_path": str(p2),
             "recipient_values": {"nama": "Sri", "email": "sri@x.com"}},
            {"index": 3, "label": "Doni", "pdf_path": str(p3),
             "recipient_values": {"nama": "Doni", "email": "budi@x.com"}},
        ],
    })
    return job_id


def test_send_butuh_gmail_terhubung(client, login, make_user, unit, done_job, session):
    user = make_user("nogmail@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id)
    login(user)
    r = client.post(f"/generate/jobs/{done_job}/send-email")
    assert r.status_code == 400
    assert "Gmail" in r.json()["detail"]


def test_send_job_unit_lain_404(client, login, make_user, done_job):
    other = make_user("lain@umbjm.ac.id", role=UserRole.admin, unit_id=999)
    login(other)
    r = client.post(f"/generate/jobs/{done_job}/send-email")
    assert r.status_code == 404


def test_send_letter_type_tanpa_email_config(client, login, admin_gmail, unit, tmp_path):
    job_store.create_job(job_id="j2", total=1, unit_id=unit.id)
    job_store.mark_done("j2", str(tmp_path / "z.zip"))
    job_store.attach_send_context("j2", {
        "letter_type_id": 1, "unit_id": unit.id, "send_email_enabled": False,
        "email_subject_template": None, "email_body_template": None,
        "email_field_key": None, "recipients": [],
    })
    login(admin_gmail)
    r = client.post("/generate/jobs/j2/send-email")
    assert r.status_code == 400


def test_send_sukses_dedupe_dan_status(client, login, admin_gmail, done_job, session, monkeypatch):
    sent = []

    def fake_send(*, refresh_token, sender, to, subject, body_text, attachments):
        sent.append({"to": to, "subject": subject, "n_attach": len(attachments), "sender": sender})
        return f"msg-{to}"

    monkeypatch.setattr(delivery_mod, "send_email", fake_send)

    login(admin_gmail)
    r = client.post(f"/generate/jobs/{done_job}/send-email")
    assert r.status_code == 200
    body = r.json()
    assert body["total_email"] == 2          # budi@x.com (x2) + sri@x.com
    assert body["total_penerima"] == 3

    # background task jalan sinkron di TestClient
    assert {s["to"] for s in sent} == {"budi@x.com", "sri@x.com"}
    budi = next(s for s in sent if s["to"] == "budi@x.com")
    assert budi["n_attach"] == 2             # 2 PDF digabung ke satu email
    assert budi["subject"] == "Surat untuk Budi"
    assert budi["sender"] == "admin@umbjm.ac.id"

    batch_id = body["send_batch_id"]
    st = client.get(f"/generate/send-batches/{batch_id}/status").json()
    assert st["total"] == 2
    assert st["sent"] == 2
    assert st["selesai"] is True

    rows = session.exec(select(Delivery)).all()
    assert all(d.status == DeliveryStatus.sent for d in rows)
    assert all(d.provider_message_id for d in rows)


def test_retry_hanya_yang_gagal(client, login, admin_gmail, done_job, session, monkeypatch):
    calls = {"n": 0}

    def flaky(*, refresh_token, sender, to, subject, body_text, attachments):
        calls["n"] += 1
        if to == "sri@x.com" and calls["n"] <= 2:
            from app.services.email_sender import EmailSenderError
            raise EmailSenderError("sesaat")
        return "ok"

    monkeypatch.setattr(delivery_mod, "send_email", flaky)

    login(admin_gmail)
    batch_id = client.post(f"/generate/jobs/{done_job}/send-email").json()["send_batch_id"]

    st = client.get(f"/generate/send-batches/{batch_id}/status").json()
    assert st["sent"] == 1 and st["failed"] == 1

    r = client.post(f"/generate/send-batches/{batch_id}/retry")
    assert r.status_code == 200
    assert r.json()["retrying"] == 1

    st2 = client.get(f"/generate/send-batches/{batch_id}/status").json()
    assert st2["sent"] == 2 and st2["failed"] == 0


def test_retry_job_kedaluwarsa_409(client, login, admin_gmail, done_job, monkeypatch):
    from app.services.email_sender import EmailSenderError

    def always_fail(**kw):
        raise EmailSenderError("sesaat")

    monkeypatch.setattr(delivery_mod, "send_email", always_fail)

    login(admin_gmail)
    batch_id = client.post(f"/generate/jobs/{done_job}/send-email").json()["send_batch_id"]
    job_store._jobs.clear()  # simulasikan job tersapu TTL 1 jam

    r = client.post(f"/generate/send-batches/{batch_id}/retry")
    assert r.status_code == 409
