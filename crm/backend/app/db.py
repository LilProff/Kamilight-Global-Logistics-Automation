from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str):
    # Render and Supabase hand out postgres:// URLs; SQLAlchemy needs the psycopg driver named
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix):]
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        # Keep connections few (Supabase's free pooler allows a limited number) and refresh them
        # before idle timeouts drop them
        kwargs |= {"pool_size": 5, "max_overflow": 3, "pool_recycle": 1800}
    return create_engine(url, **kwargs)


def harden_postgres(eng) -> None:
    """Supabase publishes public-schema tables through a web API that the (public) publishable key can call.
    Customer data must only be reachable through this app, so switch on Row Level Security and take away the
    API roles' rights on every table. The app connects as the table owner, which RLS doesn't apply to."""
    if eng.dialect.name != "postgresql":
        return
    with eng.begin() as conn:
        tables = [r[0] for r in conn.execute(text("select tablename from pg_tables where schemaname = 'public'"))]
        roles = [r[0] for r in conn.execute(text("select rolname from pg_roles where rolname in ('anon', 'authenticated')"))]
        for table in tables:
            conn.execute(text(f'alter table public."{table}" enable row level security'))
            for role in roles:
                conn.execute(text(f'revoke all on public."{table}" from {role}'))
        for role in roles:
            conn.execute(text(f"alter default privileges in schema public revoke all on tables from {role}"))
            conn.execute(text(f"alter default privileges in schema public revoke all on sequences from {role}"))


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
