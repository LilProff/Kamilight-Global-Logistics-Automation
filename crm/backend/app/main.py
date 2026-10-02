import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth import ensure_admin
from app.automations import ensure_automations
from app.config import assert_safe_to_run, get_settings
from app.db import Base, SessionLocal, engine, harden_postgres
from app.routers import auth, automations, campaigns, contacts, misc, segments, users
from app.worker import Worker

logging.basicConfig(level=logging.INFO)
STATIC = Path(__file__).resolve().parent.parent / "static"  # built frontend, copied in by the Dockerfile

# Everything the dashboard needs comes from this site itself, plus Google Fonts for the typefaces
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; object-src 'none'; "
    "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    assert_safe_to_run(get_settings())
    Base.metadata.create_all(engine)
    harden_postgres(engine)
    with SessionLocal() as db:
        ensure_admin(db)
        ensure_automations(db)
    worker = Worker() if get_settings().run_worker else None
    if worker:
        worker.start()
    yield
    if worker:
        worker.stop()


docs = get_settings().enable_docs
app = FastAPI(
    title="KGL Customer Growth System", version="1.0.0", lifespan=lifespan,
    docs_url="/docs" if docs else None, redoc_url=None, openapi_url="/openapi.json" if docs else None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "no-referrer"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    h["Content-Security-Policy"] = CSP
    if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        h["Cache-Control"] = "no-store"  # customer data must never sit in a browser or proxy cache
    return response


for r in (auth.router, users.router, contacts.router, segments.router, campaigns.router, automations.router, misc.router):
    app.include_router(r)


@app.get("/healthz")
@app.get("/health")
def health():
    """Is the app up? Kept independent of the database so Render doesn't restart-loop if the DB is down."""
    return {"ok": True}


@app.get("/health/db")
def health_db():
    """Point an uptime monitor here: fails (503) when the database can't be reached."""
    try:
        with engine.connect() as conn:
            conn.execute(text("select 1"))
    except Exception:
        raise HTTPException(503, "Database unreachable") from None
    return {"ok": True}


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        target = (STATIC / path).resolve()
        inside = target.is_relative_to(STATIC.resolve())
        return FileResponse(target if path and inside and target.is_file() else STATIC / "index.html")
