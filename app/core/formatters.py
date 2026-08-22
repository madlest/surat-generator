# Untuk format tanggal Indonesia, gunakan fungsi ini. Misal:
# from app.core.formatters import format_tanggal_indonesia

from datetime import date
import re


def format_tanggal_indonesia(d: date) -> str:
    """
    Format objek date jadi string tanggal Indonesia tanpa leading zero,
    misal: date(2026, 9, 1) -> "1 September 2026"

    Catatan: nama bulan (%B) bergantung pada locale 'id_ID.UTF-8' yang
    di-set di core/config.py. Pastikan config.py sudah ter-import
    (biasanya otomatis karena hampir semua module import dari situ)
    sebelum fungsi ini dipanggil.
    """
    return f"{d.day} {d.strftime('%B')} {d.year}"

def sanitize_filename(name: str) -> str:
    """
    Hapus/ganti karakter yang tidak valid di nama file Windows,
    supaya file yang dihasilkan aman dibuka di OS mana pun.
    Karakter terlarang di Windows: \\ / : * ? " < > |
    """
    return re.sub(r'[\\/:*?"<>|]', '', name)


def build_recipient_filename(nama_dosen: str, mata_kuliah: str, semester: str) -> str:
    """
    Bangun nama file PDF per recipient, format:
    "{Nama Dosen} - {Mata Kuliah} - Semester {Semester}.pdf"
    """
    raw_name = f"{nama_dosen} - {mata_kuliah} - Semester {semester}"
    return f"{sanitize_filename(raw_name)}.pdf"