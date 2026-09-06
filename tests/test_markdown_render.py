"""app/services/markdown_render.py + endpoint /admin/letter-types/preview-email."""
from app.services.delivery import render_template
from app.services.markdown_render import markdown_to_email_html


def test_render_list_dan_inline():
    html = markdown_to_email_html("**tebal** _miring_\n\n- a\n- b\n\n1. x\n2. y")
    assert "<strong>tebal</strong>" in html
    assert "<em>miring</em>" in html
    assert "<ul>" in html and "<li>a</li>" in html
    assert "<ol>" in html and "<li>x</li>" in html


def test_render_escape_html_mentah():
    # Tag HTML di sumber TIDAK diteruskan (netralisasi injeksi lewat {placeholder}).
    html = markdown_to_email_html("halo <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_autolink_url():
    assert '<a href="https://umbjm.ac.id">' in markdown_to_email_html("cek https://umbjm.ac.id")


def test_render_template_md_escape():
    # Nama "A_B" tidak boleh jadi miring saat masuk badan email.
    out = render_template("Yth. {nama}", {"nama": "A_B*C"}, md_escape=True)
    assert out == r"Yth. A\_B\*C"
    # tanpa md_escape (subjek / WA): apa adanya
    assert render_template("Yth. {nama}", {"nama": "A_B*C"}) == "Yth. A_B*C"


def test_preview_email_endpoint(client, login, make_user):
    login(make_user("admin@umbjm.ac.id"))
    r = client.post("/admin/letter-types/preview-email", data={"markdown": "# Judul\n\n- satu"})
    assert r.status_code == 200
    html = r.json()["html"]
    assert "<h1>Judul</h1>" in html and "<li>satu</li>" in html


def test_preview_email_butuh_login(client):
    assert client.post("/admin/letter-types/preview-email", data={"markdown": "x"}).status_code == 401
