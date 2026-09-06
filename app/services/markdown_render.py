"""
Render Markdown badan email → HTML. Dipakai DUA tempat dengan renderer yang
sama persis: endpoint pratinjau di wizard dan pengiriman sesungguhnya di
`delivery.py` — jadi yang dilihat admin = yang diterima penerima.

`html=False`: tag HTML mentah di sumber di-escape, bukan diteruskan. Ini yang
menetralkan injeksi lewat placeholder `{nama}` (mis. nilai field berisi
`<script>`), tanpa perlu sanitizer terpisah.
"""
from markdown_it import MarkdownIt

_md = MarkdownIt("commonmark", {"html": False, "linkify": True, "breaks": True})
_md.enable("linkify")

# Wrapper + gaya inline seadanya supaya tampil wajar di mayoritas klien email
# (banyak yang mengabaikan <style> di <head>, jadi style ditempel di elemen).
_WRAPPER = (
    '<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;'
    'font-size:15px;line-height:1.6;color:#1b2a2e;max-width:640px">{body}</div>'
)


def markdown_to_email_html(md_text: str) -> str:
    return _WRAPPER.format(body=_md.render(md_text or ""))
