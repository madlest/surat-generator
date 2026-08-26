# Formatters untuk keperluan surat, misal format tanggal, nama file, dsb.

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


def build_generic_recipient_filename(label: str, index: int) -> str:
    """
    Bangun nama file PDF per recipient untuk jenis surat dinamis,
    dari label gabungan nilai field-field recipient (mis. "Budi - Farmakologi").
    """
    return sanitize_filename(label) if label else f"Penerima {index}"


def angka_ke_terbilang(n: int) -> str:
    """
    Ubah angka non-negatif jadi kata bilangan Bahasa Indonesia.
    Mendukung sampai ratusan, cukup untuk rentang wajar jumlah lampiran.
    """
    satuan = ["", "satu", "dua", "tiga", "empat", "lima", "enam", "tujuh", "delapan", "sembilan"]

    if n == 0:
        return "nol"
    if n < 10:
        return satuan[n]
    if n < 20:
        return angka_ke_terbilang(n - 10) + " belas"
    if n < 100:
        sisa = n % 10
        return angka_ke_terbilang(n // 10) + " puluh" + (f" {angka_ke_terbilang(sisa)}" if sisa else "")
    if n < 200:
        sisa = n - 100
        return "seratus" + (f" {angka_ke_terbilang(sisa)}" if sisa else "")
    if n < 1000:
        sisa = n % 100
        return angka_ke_terbilang(n // 100) + " ratus" + (f" {angka_ke_terbilang(sisa)}" if sisa else "")
    raise ValueError("angka_ke_terbilang hanya mendukung angka di bawah 1000")


def format_jumlah_lampiran(jumlah: int) -> str:
    """
    Format jumlah lampiran sesuai konvensi surat resmi Indonesia:
    "3 (tiga) berkas", atau "-" kalau tidak ada lampiran sama sekali.
    """
    if jumlah == 0:
        return "-"
    return f"{jumlah} ({angka_ke_terbilang(jumlah)}) berkas"