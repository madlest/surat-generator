# core/config.py
import locale

try:
    locale.setlocale(locale.LC_TIME, 'id_ID.UTF-8')
except locale.Error:
    raise RuntimeError(
        "Locale 'id_ID.UTF-8' belum terinstall di sistem ini. "
        "Jalankan: sudo locale-gen id_ID.UTF-8 && sudo update-locale"
    )