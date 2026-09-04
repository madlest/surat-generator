from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from app.routers import admin, auth, generate, superadmin

app = FastAPI(title="Surat Generator")

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
