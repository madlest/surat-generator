from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.database import init_db
from app.routers import permohonan_mengajar, admin, generate

app = FastAPI(title="Surat Generator")

init_db()

app.include_router(permohonan_mengajar.router)
app.include_router(admin.router)
app.include_router(generate.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html")