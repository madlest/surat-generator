"""
Endpoint Stage C: POST /generate/jobs/{id}/whatsapp, POST /generate/deliveries/{id}/mark.
"""
import pytest
from sqlmodel import select

from app.core.job_store import job_store
from app.models.delivery import Delivery, DeliveryStatus
from app.models.organization import Unit, User, UserRole


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
def admin(session, unit):
    user = User(email="admin@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture()
def wa_job(unit):
    job_id = "job-wa"
    job_store.create_job(job_id=job_id, total=3, unit_id=unit.id)
    job_store.mark_done(job_id, "/tmp/hasil.zip")
    job_store.attach_send_context(job_id, {
        "letter_type_id": 1,
        "unit_id": unit.id,
        "send_email_enabled": False,
        "email_field_key": None,
        "send_whatsapp_enabled": True,
        "whatsapp_message_template": "Halo {nama}, surat Anda siap.",
        "phone_field_key": "nomor_wa",
        "recipients": [
            {"index": 1, "label": "Budi", "pdf_path": "/tmp/1.pdf",
             "recipient_values": {"nomor_wa": "+6281111", "nama": "Budi"},
             "render_values": {"nama": "Budi"}},
            {"index": 2, "label": "Sri", "pdf_path": "/tmp/2.pdf",
             "recipient_values": {"nomor_wa": "+6282222", "nama": "Sri"},
             "render_values": {"nama": "Sri"}},
            {"index": 3, "label": "Budi", "pdf_path": "/tmp/3.pdf",
             "recipient_values": {"nomor_wa": "+6281111", "nama": "Budi"},
             "render_values": {"nama": "Budi"}},
        ],
    })
    return job_id


def test_prepare_wa_butuh_config(client, login, admin, unit):
    job_store.create_job(job_id="j0", total=1, unit_id=unit.id)
    job_store.mark_done("j0", "/tmp/z.zip")
    job_store.attach_send_context("j0", {
        "letter_type_id": 1, "unit_id": unit.id, "send_whatsapp_enabled": False,
        "phone_field_key": None, "recipients": [],
    })
    login(admin)
    assert client.post("/generate/jobs/j0/whatsapp").status_code == 400


def test_prepare_wa_job_unit_lain_404(client, login, make_user, wa_job):
    login(make_user("lain@umbjm.ac.id", role=UserRole.admin, unit_id=999))
    assert client.post(f"/generate/jobs/{wa_job}/whatsapp").status_code == 404


def test_prepare_wa_dedupe_dan_url(client, login, admin, wa_job, session):
    login(admin)
    r = client.post(f"/generate/jobs/{wa_job}/whatsapp")
    assert r.status_code == 200
    body = r.json()
    assert body["total_wa"] == 2  # +6281111 (x2) + +6282222
    assert body["total_penerima"] == 3

    d = body["deliveries"]
    assert {x["kontak"] for x in d} == {"+6281111", "+6282222"}
    budi = next(x for x in d if x["kontak"] == "+6281111")
    assert budi["wa_url"].startswith("https://wa.me/6281111?text=")
    assert budi["status"] == "pending"

    rows = session.exec(select(Delivery)).all()
    assert len(rows) == 2
    assert all(row.channel.value == "whatsapp" for row in rows)


def test_mark_delivery_toggle(client, login, admin, wa_job, session):
    login(admin)
    did = client.post(f"/generate/jobs/{wa_job}/whatsapp").json()["deliveries"][0]["id"]

    assert client.post(f"/generate/deliveries/{did}/mark", data={"sent": "true"}).json()["status"] == "sent"
    session.expire_all()
    assert session.get(Delivery, did).status == DeliveryStatus.sent
    assert session.get(Delivery, did).sent_at is not None

    assert client.post(f"/generate/deliveries/{did}/mark", data={"sent": "false"}).json()["status"] == "pending"
    session.expire_all()
    assert session.get(Delivery, did).sent_at is None


def test_mark_delivery_unit_lain_404(client, login, admin, make_user, wa_job):
    login(admin)
    did = client.post(f"/generate/jobs/{wa_job}/whatsapp").json()["deliveries"][0]["id"]
    login(make_user("lain@umbjm.ac.id", role=UserRole.admin, unit_id=999))
    assert client.post(f"/generate/deliveries/{did}/mark", data={"sent": "true"}).status_code == 404


def test_wa_status_lewat_send_batches(client, login, admin, wa_job):
    login(admin)
    batch = client.post(f"/generate/jobs/{wa_job}/whatsapp").json()["send_batch_id"]
    st = client.get(f"/generate/send-batches/{batch}/status").json()
    assert st["total"] == 2
    assert st["pending"] == 2
    assert st["selesai"] is False
