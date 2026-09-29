import os
import tempfile

# Must be set before the app (and its engine) is imported
_tmp = tempfile.mkdtemp()
# Set TEST_DATABASE_URL to run the suite against Postgres (the production database type)
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["RUN_WORKER"] = "false"
os.environ["WA_TOKEN"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["ADMIN_EMAIL"] = "admin@test.local"
os.environ["ADMIN_PASSWORD"] = "pw"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        token = c.post("/api/auth/login", json={"email": "admin@test.local", "password": "pw"}).json()["token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c
