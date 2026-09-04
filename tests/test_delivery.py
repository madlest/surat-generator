"""app/services/delivery.py — render template, dedupe, jalankan batch kirim."""
import json

import pytest
from sqlmodel import select

from app.models.delivery import Delivery, DeliveryStatus
from app.services import delivery as delivery_mod
from app.services.delivery import (
    create_delivery_rows,
    plan_email_deliveries,
    render_template,
    run_email_send_batch,
)
from app.services.email_sender import EmailSenderError, GmailAuthExpired


# --- render_template ---------------------------------------------------

def test_render_ganti_placeholder():
    assert render_template("Yth. {nama} di {kota}", {"nama": "Budi", "kota": "Banjarmasin"}) == (
        "Yth. Budi di Banjarmasin"
    )


def test_render_key_hilang_jadi_kosong():
    assert render_template("Hai {nama}{gelar}", {"nama": "Sri"}) == "Hai Sri"


def test_render_none_jadi_kosong():
    assert render_template("[{x}]", {"x": None}) == "[]"


def test_render_kurung_tak_berpasangan_aman():
    # tidak melempar (beda dari str.format)
    assert render_template("50% { diskon {nama}", {"nama": "A"}) == "50% { diskon A"


# --- plan_email_deliveries -------------------------------------------

def _manifest(*rows):
    return [
        {"index": i + 1, "label": lbl, "pdf_path": path, "recipient_values": vals}
        for i, (lbl, path, vals) in enumerate(rows)
    ]


def test_plan_satu_penerima_satu_email():
    m = _manifest(
        ("Budi", "/tmp/a.pdf", {"email": "budi@x.com", "nama": "Budi"}),
        ("Sri", "/tmp/b.pdf", {"email": "sri@x.com", "nama": "Sri"}),
    )
    plans = plan_email_deliveries(m, "email", "Surat untuk {nama}", "Halo {nama}")
    assert [p["contact"] for p in plans] == ["budi@x.com", "sri@x.com"]
    assert plans[0]["subject"] == "Surat untuk Budi"
    assert plans[0]["attachment_names"] == ["a.pdf"]


def test_plan_dedupe_email_sama():
    m = _manifest(
        ("Budi", "/tmp/a.pdf", {"email": "SAMA@x.com", "nama": "Budi"}),
        ("Sri", "/tmp/b.pdf", {"email": "sama@x.com", "nama": "Sri"}),
    )
    plans = plan_email_deliveries(m, "email", "S", "B")
    assert len(plans) == 1
    assert plans[0]["contact"] == "sama@x.com"
    assert plans[0]["pdf_paths"] == ["/tmp/a.pdf", "/tmp/b.pdf"]
    assert plans[0]["label"] == "Budi, Sri"  # label digabung


def test_plan_lewati_tanpa_email():
    m = _manifest(("Budi", "/tmp/a.pdf", {"email": "", "nama": "Budi"}))
    assert plan_email_deliveries(m, "email", "S", "B") == []


# --- run_email_send_batch ------------------------------------------

@pytest.fixture()
def pdfs(tmp_path):
    p1 = tmp_path / "surat1.pdf"
    p2 = tmp_path / "surat2.pdf"
    p1.write_bytes(b"%PDF-1.4 satu")
    p2.write_bytes(b"%PDF-1.4 dua")
    return str(p1), str(p2)


def _mk_rows(session, n, job_id="job1"):
    planned = [
        {
            "contact": f"orang{i}@x.com",
            "label": f"Orang {i}",
            "subject": "S",
            "body": "B",
            "pdf_paths": [],
            "attachment_names": [],
        }
        for i in range(n)
    ]
    return create_delivery_rows(
        session,
        planned=planned,
        letter_type_id=1,
        unit_id=1,
        send_batch_id="batch1",
        job_id=job_id,
        triggered_by_user_id=1,
    )


def test_run_batch_status_campuran(session, engine, monkeypatch, pdfs):
    rows = _mk_rows(session, 3)

    def fake_send(*, refresh_token, sender, to, subject, body_text, attachments):
        if to == "orang0@x.com":
            return "msg-ok"
        if to == "orang1@x.com":
            raise GmailAuthExpired("izin habis")
        raise EmailSenderError("5xx")

    monkeypatch.setattr(delivery_mod, "send_email", fake_send)

    payloads = [
        {"delivery_id": r.id, "contact": r.recipient_contact, "subject": "S", "body": "B",
         "pdf_paths": [pdfs[0]]}
        for r in rows
    ]
    run_email_send_batch(engine, payloads=payloads, refresh_token="r", sender="a@umbjm.ac.id")

    session.expire_all()
    got = {r.recipient_contact: r for r in session.exec(select(Delivery)).all()}
    assert got["orang0@x.com"].status == DeliveryStatus.sent
    assert got["orang0@x.com"].provider_message_id == "msg-ok"
    assert got["orang0@x.com"].sent_at is not None
    assert got["orang1@x.com"].status == DeliveryStatus.auth_expired
    assert got["orang2@x.com"].status == DeliveryStatus.failed
    assert "5xx" in got["orang2@x.com"].error_message


def test_run_batch_file_hilang_jadi_failed(session, engine, monkeypatch):
    rows = _mk_rows(session, 1)
    monkeypatch.setattr(delivery_mod, "send_email", lambda **kw: "x")
    payloads = [
        {"delivery_id": rows[0].id, "contact": "z@x.com", "subject": "S", "body": "B",
         "pdf_paths": ["/tidak/ada/file.pdf"]}
    ]
    run_email_send_batch(engine, payloads=payloads, refresh_token="r", sender="a@umbjm.ac.id")
    session.expire_all()
    assert session.get(Delivery, rows[0].id).status == DeliveryStatus.failed


def test_create_delivery_rows_isi_kolom(session):
    rows = _mk_rows(session, 1)
    r = session.get(Delivery, rows[0].id)
    assert r.status == DeliveryStatus.pending
    assert r.channel.value == "email"
    assert r.send_batch_id == "batch1"
    assert json.loads(r.attachment_names) == []
