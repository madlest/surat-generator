from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class DeliveryChannel(str, Enum):
    email = "email"
    whatsapp = "whatsapp"  # disiapkan untuk Stage C (wa.me) — belum dipakai


class DeliveryStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    # Kegagalan sesaat (jaringan, 5xx, respons aneh) — boleh dikirim ulang.
    failed = "failed"
    # Refresh token Gmail ditolak Google. Admin harus menghubungkan ulang
    # Gmail dulu; retry sebelum itu percuma. Dibedakan dari `failed` supaya UI
    # bisa mengarahkan ke tombol "Hubungkan Gmail", bukan cuma "Coba lagi".
    auth_expired = "auth_expired"


class Delivery(SQLModel, table=True):
    """
    Satu upaya mengirim satu-atau-lebih PDF surat ke SATU kontak lewat satu
    channel.

    Sengaja trigger-agnostic: `job_id` menautkan baris ini ke batch generate
    yang memicunya sekarang, tapi portal mahasiswa nanti akan jadi pemicu lain
    (lewat `LetterRequest`) tanpa perlu mengubah tabel ini — makanya `job_id`
    nullable dan tidak ada FK ke sana.

    Isi email (subject/body/lampiran) disimpan sebagai snapshot: kalau template
    di LetterType diubah setelah pengiriman, riwayat tetap mencerminkan apa
    yang benar-benar dikirim.
    """

    id: int | None = Field(default=None, primary_key=True)

    letter_type_id: int = Field(foreign_key="lettertype.id", index=True)
    # Didenormalisasi dari LetterType.unit_id supaya cek isolasi antar-unit di
    # endpoint status/retry tidak perlu join tiap kali — sama pola dengan
    # unit_id yang disimpan di job_store.
    unit_id: int = Field(foreign_key="unit.id", index=True)

    channel: DeliveryChannel

    # Pengelompok satu aksi "Kirim" (sekali klik tombol). Semua Delivery dari
    # aksi itu berbagi nilai ini. Bukan FK; tidak ada tabel SendBatch sendiri.
    send_batch_id: str = Field(index=True)
    # Job generate in-memory yang memicu. None untuk pemicu non-batch.
    job_id: str | None = Field(default=None)

    recipient_contact: str  # email (sudah lowercase) atau nomor +62…
    recipient_label: str    # nama penerima untuk ditampilkan di UI/riwayat

    subject: str | None = Field(default=None)
    body: str | None = Field(default=None)
    attachment_names: str = Field(default="[]")  # JSON list nama file

    status: DeliveryStatus = Field(default=DeliveryStatus.pending, index=True)
    error_message: str | None = Field(default=None)
    provider_message_id: str | None = Field(default=None)  # id pesan Gmail

    triggered_by_user_id: int = Field(foreign_key="user.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: datetime | None = Field(default=None)
