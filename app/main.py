# Fungsi main untuk FastAPI

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import permohonan_mengajar

app = FastAPI(title="Surat Generator")

app.include_router(permohonan_mengajar.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html")