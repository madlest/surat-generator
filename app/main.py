import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.core.config import settings
from app.routers import admin, auth, generate, superadmin


def _clear_orphan_job_dirs() -> None:
    """
    Job disimpan di memori, jadi setelah restart semua job lama hilang tetapi
    folder kerjanya (PDF + ZIP) tertinggal di temp_dir dan tidak pernah
    dibersihkan. Karena tidak ada job yang bisa diunduh lagi, aman dihapus.
    """
    for job_dir in Path(settings.temp_dir).glob("job_*"):
        shutil.rmtree(job_dir, ignore_errors=True)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _clear_orphan_job_dirs()
    yield


app = FastAPI(title="Surat Generator", lifespan=lifespan)

# HTML/CSS/JS dikirim tanpa build step, jadi kompresi di sini memangkas
# transfer ~70%. File ZIP/PDF hasil generate sudah terkompres dan dilewati
# karena ukurannya tak turun berarti — cukup respons teks di atas 1 KB.
app.add_middleware(GZipMiddleware, minimum_size=1024)

app.include_router(auth.router)
app.include_router(superadmin.router)
app.include_router(admin.router)
app.include_router(generate.router)


class NoCacheStaticFiles(StaticFiles):
    """
    StaticFiles yang selalu menyuruh browser revalidasi (Cache-Control:
    no-cache) alih-alih menyimpan asset diam-diam pakai heuristik.

    Aplikasi ini tanpa build step / hashing nama file — style.css & modul JS
    dipakai apa adanya. Tanpa ini, setelah deploy browser bisa menahan versi
    lama berjam-jam dan admin melihat UI yang tidak cocok dengan backend.
    `no-cache` tetap memakai ETag: kalau file tak berubah, responsnya 304
    (murah), kalau berubah langsung terambil yang baru.
    """

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/static", NoCacheStaticFiles(directory="app/static"), name="static")

_NO_CACHE = {"Cache-Control": "no-cache"}


@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html", headers=_NO_CACHE)


@app.get("/privacy")
def serve_privacy():
    # Halaman publik (tanpa login) — URL-nya dipakai di OAuth consent screen
    # Google sebagai "Application privacy policy link".
    return FileResponse("app/static/privacy.html", headers=_NO_CACHE)
