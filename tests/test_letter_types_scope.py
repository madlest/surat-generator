"""
Test scoping jenis surat lintas unit (Stage 4 / B3).

Fokus: superadmin bisa membedakan dua unit yang memakai slug jenis surat sama
lewat ?unit_slug=, dan admin biasa tidak bisa memakai param itu untuk mengintip
unit lain.

LetterType dibuat langsung lewat session (bukan endpoint) supaya tidak perlu
mengunggah docx sungguhan — yang diuji di sini murni logika scoping.
"""
import pytest

from app.models.letter_type import LetterType
from app.models.organization import Unit, UserRole


@pytest.fixture()
def units(session):
    farmasi = Unit(slug="farmasi", name="Fakultas Farmasi")
    hukum = Unit(slug="hukum", name="Fakultas Hukum")
    session.add_all([farmasi, hukum])
    session.commit()
    session.refresh(farmasi)
    session.refresh(hukum)
    return {"farmasi": farmasi, "hukum": hukum}


@pytest.fixture()
def spm_di_dua_unit(session, units):
    session.add_all(
        [
            LetterType(slug="spm", name="SPM Farmasi", template_path="p/farmasi/spm.docx", unit_id=units["farmasi"].id),
            LetterType(slug="spm", name="SPM Hukum", template_path="p/hukum/spm.docx", unit_id=units["hukum"].id),
        ]
    )
    session.commit()
    return units


def _login_super(login, make_user):
    login(make_user("super@umbjm.ac.id", role=UserRole.superadmin))


def _login_admin(login, make_user, unit):
    login(make_user("admin@umbjm.ac.id", role=UserRole.admin, unit_id=unit.id))


# --- daftar --------------------------------------------------------------

def test_list_menyertakan_unit_slug_dan_unit_name(client, login, make_user, spm_di_dua_unit):
    _login_super(login, make_user)
    rows = client.get("/admin/letter-types").json()
    assert len(rows) == 2
    by_unit = {r["unit_slug"]: r for r in rows}
    assert by_unit["farmasi"]["name"] == "SPM Farmasi"
    assert by_unit["farmasi"]["unit_name"] == "Fakultas Farmasi"
    assert by_unit["hukum"]["unit_name"] == "Fakultas Hukum"


def test_admin_biasa_hanya_melihat_unitnya(client, login, make_user, spm_di_dua_unit):
    _login_admin(login, make_user, spm_di_dua_unit["farmasi"])
    rows = client.get("/admin/letter-types").json()
    assert [r["unit_slug"] for r in rows] == ["farmasi"]


def test_archived_list_juga_menyertakan_unit(client, login, make_user, session, units):
    lt = LetterType(
        slug="lama", name="Jenis Lama", template_path="p/farmasi/lama.docx",
        unit_id=units["farmasi"].id,
    )
    session.add(lt)
    session.commit()
    session.refresh(lt)
    # tandai terarsip
    from datetime import datetime

    lt.deleted_at = datetime.utcnow()
    session.add(lt)
    session.commit()

    _login_super(login, make_user)
    rows = client.get("/admin/letter-types/archived").json()
    assert len(rows) == 1
    assert rows[0]["unit_slug"] == "farmasi"


# --- disambiguasi by unit_slug -----------------------------------------

def test_superadmin_ambil_per_unit_slug(client, login, make_user, spm_di_dua_unit):
    _login_super(login, make_user)
    assert client.get("/admin/letter-types/spm?unit_slug=farmasi").json()["name"] == "SPM Farmasi"
    assert client.get("/admin/letter-types/spm?unit_slug=hukum").json()["name"] == "SPM Hukum"


def test_superadmin_unit_slug_tidak_dikenal_404(client, login, make_user, spm_di_dua_unit):
    _login_super(login, make_user)
    assert client.get("/admin/letter-types/spm?unit_slug=tidakada").status_code == 404


def test_admin_biasa_tidak_bisa_intip_unit_lain_lewat_param(client, login, make_user, session, units):
    # hanya hukum yang punya "rahasia"
    session.add(
        LetterType(slug="rahasia", name="Rahasia Hukum", template_path="p/hukum/rahasia.docx", unit_id=units["hukum"].id)
    )
    session.commit()

    _login_admin(login, make_user, units["farmasi"])
    assert client.get("/admin/letter-types/rahasia?unit_slug=hukum").status_code == 404


def test_admin_biasa_param_unit_lain_diabaikan_bukan_dipakai(client, login, make_user, spm_di_dua_unit):
    # admin farmasi minta ?unit_slug=hukum -> param diabaikan total, tetap
    # dapat SPM milik farmasi sendiri (bukan milik hukum).
    _login_admin(login, make_user, spm_di_dua_unit["farmasi"])
    body = client.get("/admin/letter-types/spm?unit_slug=hukum").json()
    assert body["name"] == "SPM Farmasi"
