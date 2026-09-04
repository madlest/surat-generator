"""
Orkestrasi kirim surat lewat email (Stage B4): rencanakan pengiriman dari
manifest hasil generate, buat baris `Delivery`, lalu jalankan pengiriman satu
per satu di background sambil memperbarui status tiap baris.

Yang di sini murni soal orkestrasi (dedupe, template, status, retry). Transport
sesungguhnya ada di `email_sender.py`; definisi field / parsing nilai ada di
`dynamic_fields.py`.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import Session, select

from app.models.delivery import Delivery, DeliveryChannel, DeliveryStatus
from app.services.email_sender import EmailSenderError, GmailAuthExpired, send_email

# Placeholder di template subjek/badan: {nama_field}. Kurung yang tidak
# berpasangan / isi aneh dibiarkan apa adanya (tidak melempar), beda dari
# str.format yang rewel.
_PLACEHOLDER_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def render_template(template: str, values: dict) -> str:
    """Ganti tiap `{key}` dengan `values[key]`. Key tak dikenal → string
    kosong. `None` → string kosong."""
    def _sub(match: re.Match) -> str:
        val = values.get(match.group(1))
        return "" if val is None else str(val)

    return _PLACEHOLDER_RE.sub(_sub, template or "")


def plan_email_deliveries(
    recipients_manifest: list[dict],
    email_field_key: str,
    subject_template: str,
    body_template: str,
) -> list[dict]:
    """
    Dari manifest generate (`[{index, label, pdf_path, recipient_values}]`)
    susun daftar pengiriman email, DIDEDUPE per alamat: satu email unik = satu
    kiriman dengan SEMUA PDF-nya dilampirkan.

    Subjek & badan dirender dari nilai penerima yang PERTAMA muncul untuk email
    itu (kasus umum: satu email = satu penerima). Label penerima yang berbagi
    email digabung untuk tampilan.

    Return: `[{contact, label, subject, body, pdf_paths, attachment_names}]`,
    urut sesuai kemunculan pertama.
    """
    by_email: dict[str, dict] = {}
    labels_seen: dict[str, list[str]] = {}

    for item in recipients_manifest:
        values = item.get("recipient_values", {})
        # Untuk merender subjek/badan: pakai render_values (batch + penerima,
        # sudah diformat) kalau ada; fallback ke nilai penerima mentah.
        render_values = item.get("render_values", values)
        raw = values.get(email_field_key)
        if not raw:
            continue  # penerima tanpa email — dilewati (UI mestinya sudah cegah)
        email = str(raw).strip().lower()
        pdf_path = item["pdf_path"]
        pdf_name = Path(pdf_path).name
        label = (item.get("label") or "").strip()

        if email not in by_email:
            by_email[email] = {
                "contact": email,
                "label": label or email,
                "subject": render_template(subject_template, render_values),
                "body": render_template(body_template, render_values),
                "pdf_paths": [],
                "attachment_names": [],
            }
            labels_seen[email] = []

        by_email[email]["pdf_paths"].append(pdf_path)
        by_email[email]["attachment_names"].append(pdf_name)
        if label and label not in labels_seen[email]:
            labels_seen[email].append(label)

    for email, plan in by_email.items():
        if len(labels_seen[email]) > 1:
            plan["label"] = ", ".join(labels_seen[email])

    return list(by_email.values())


def create_delivery_rows(
    session: Session,
    *,
    planned: list[dict],
    letter_type_id: int,
    unit_id: int,
    send_batch_id: str,
    job_id: str | None,
    triggered_by_user_id: int,
) -> list[Delivery]:
    """Buat satu baris Delivery berstatus `pending` per entri `planned`.
    Urutan baris hasil sama dengan `planned`."""
    rows: list[Delivery] = []
    for plan in planned:
        row = Delivery(
            letter_type_id=letter_type_id,
            unit_id=unit_id,
            channel=DeliveryChannel.email,
            send_batch_id=send_batch_id,
            job_id=job_id,
            recipient_contact=plan["contact"],
            recipient_label=plan["label"],
            subject=plan["subject"],
            body=plan["body"],
            attachment_names=json.dumps(plan["attachment_names"], ensure_ascii=False),
            status=DeliveryStatus.pending,
            triggered_by_user_id=triggered_by_user_id,
        )
        session.add(row)
        rows.append(row)
    session.commit()
    for row in rows:
        session.refresh(row)
    return rows


def _finish(engine, delivery_id: int, status: DeliveryStatus, *, message_id="", error=None) -> None:
    with Session(engine) as session:
        row = session.get(Delivery, delivery_id)
        if row is None:
            return
        row.status = status
        row.error_message = error
        row.provider_message_id = message_id or None
        if status == DeliveryStatus.sent:
            row.sent_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()


def run_email_send_batch(engine, *, payloads: list[dict], refresh_token: str, sender: str) -> None:
    """
    Background task: kirim tiap payload lewat Gmail, perbarui baris Delivery.

    payload: `{delivery_id, contact, subject, body, pdf_paths}`.

    Kegagalan satu penerima tidak menghentikan yang lain. `GmailAuthExpired`
    pada satu penerima kemungkinan besar akan berulang untuk sisanya (token
    yang sama), tapi tetap dicoba semua supaya statusnya akurat per baris.
    """
    for item in payloads:
        try:
            attachments: list[tuple[str, bytes]] = []
            for path in item["pdf_paths"]:
                attachments.append((Path(path).name, Path(path).read_bytes()))

            message_id = send_email(
                refresh_token=refresh_token,
                sender=sender,
                to=item["contact"],
                subject=item["subject"] or "",
                body_text=item["body"] or "",
                attachments=attachments,
            )
            _finish(engine, item["delivery_id"], DeliveryStatus.sent, message_id=message_id)
        except GmailAuthExpired as exc:
            _finish(engine, item["delivery_id"], DeliveryStatus.auth_expired, error=str(exc))
        except (EmailSenderError, OSError) as exc:
            _finish(engine, item["delivery_id"], DeliveryStatus.failed, error=str(exc))


def deliveries_for_batch(session: Session, send_batch_id: str) -> list[Delivery]:
    return list(
        session.exec(
            select(Delivery)
            .where(Delivery.send_batch_id == send_batch_id)
            .order_by(Delivery.id)
        ).all()
    )
