from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import admin, auth, generate

app = FastAPI(title="Surat Generator")

app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(generate.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/")
def serve_frontend():
    return FileResponse("app/static/index.html")