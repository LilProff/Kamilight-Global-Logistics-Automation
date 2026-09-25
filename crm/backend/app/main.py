import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import Base, engine
from app.routers import campaigns, contacts, misc, segments
from app.worker import Worker

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).resolve().parent.parent / "static"  # built frontend, copied in by the Dockerfile


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    worker = Worker() if get_settings().run_worker else None
    if worker:
        worker.start()
    yield
    if worker:
        worker.stop()


app = FastAPI(title="KGL Customer Growth System", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
for r in (contacts.router, segments.router, campaigns.router, misc.router):
    app.include_router(r)


@app.get("/health")
def health():
    return {"ok": True}


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (STATIC / path).resolve()
        inside = target.is_relative_to(STATIC.resolve())
        return FileResponse(target if path and inside and target.is_file() else STATIC / "index.html")
