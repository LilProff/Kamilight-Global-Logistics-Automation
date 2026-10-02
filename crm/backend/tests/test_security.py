import pytest
from fastapi.testclient import TestClient

from app.config import Settings, assert_safe_to_run, get_settings
from app.main import app
from app.security import hash_password, password_problem, verify_password


def _login(c, email="admin@test.local", password="pw"):
    return c.post("/api/auth/login", json={"email": email, "password": password})


def _as(c, email, password):
    r = _login(c, email, password)
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"


def test_password_hashing_is_salted_and_verifiable():
    a, b = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert a != b and a.startswith("scrypt$")  # different salts
    assert verify_password("correct horse battery", a) and not verify_password("wrong", a)
    assert not verify_password("x", "garbage") and not verify_password("x", "scrypt$1$2")


@pytest.mark.parametrize("pw,email,ok", [
    ("short", "", False), ("password", "", False), ("aaaaaaaaaaaa", "", False),
    ("ada@example.com", "ada@example.com", False), ("MyTundeSecret2026!", "tunde@example.com", False),  # contains the name part
    ("river-Lantern-47-moss", "tunde@example.com", True), ("MyAdaSecret2026!", "ada@example.com", True),  # 3-letter names aren't blocked
])
def test_password_rules(pw, email, ok):
    assert (password_problem(pw, email) is None) is ok


def test_admin_is_seeded_from_settings_and_login_returns_profile(client):
    me = client.get("/api/auth/me").json()
    assert me["email"] == "admin@test.local" and me["role"] == "admin"
    r = _login(client, "ADMIN@test.local ", "pw")  # case and stray spaces don't matter
    assert r.status_code == 200 and r.json()["role"] == "admin"


def test_login_lockout_after_repeated_failures_and_resets_on_success(client):
    s = get_settings()
    for _ in range(s.login_max_failures):
        assert _login(client, "admin@test.local", "nope").status_code == 401
    locked = _login(client, "admin@test.local", "pw")  # even the right password is refused while locked
    assert locked.status_code == 429 and "Too many failed attempts" in locked.json()["detail"]
    assert "retry-after" in {k.lower() for k in locked.headers}
    # unknown emails are counted too, and look the same as a wrong password
    for _ in range(s.login_max_failures):
        assert _login(client, "ghost@test.local", "x").json()["detail"] == "Email or password is wrong."
    assert _login(client, "ghost@test.local", "x").status_code == 429


def test_successful_login_clears_earlier_failures(client):
    for _ in range(3):
        _login(client, "admin@test.local", "nope")
    assert _login(client, "admin@test.local", "pw").status_code == 200
    for _ in range(3):  # would be 6 failures in total without the reset
        assert _login(client, "admin@test.local", "nope").status_code == 401


def test_team_management_and_roles(client):
    assert client.post("/api/users", json={"email": "tunde@test.local", "name": "Tunde", "role": "staff", "password": "short"}).status_code == 422
    r = client.post("/api/users", json={"email": "Tunde@test.local", "name": "Tunde", "role": "staff", "password": "river-Lantern-47-moss"})
    assert r.status_code == 201 and r.json()["email"] == "tunde@test.local"
    assert client.post("/api/users", json={"email": "tunde@test.local", "password": "river-Lantern-47-moss"}).status_code == 409
    uid = r.json()["id"]

    with TestClient(app) as staff:  # a second browser
        _as(staff, "tunde@test.local", "river-Lantern-47-moss")
        assert staff.post("/api/contacts/search", json={}).status_code == 200  # staff can work with customers
        assert staff.get("/api/users").status_code == 403 and staff.post("/api/users", json={}).status_code in (403, 422)
        assert staff.put("/api/automations/winback", json={"enabled": False}).status_code == 403
        # deactivating signs them out immediately
        assert client.patch(f"/api/users/{uid}", json={"active": False}).status_code == 200
        assert staff.post("/api/contacts/search", json={}).status_code == 401
    assert _login(client, "tunde@test.local", "river-Lantern-47-moss").status_code == 401


def test_cannot_remove_the_last_administrator(client):
    admin_id = client.get("/api/auth/me").json()["id"]
    assert client.patch(f"/api/users/{admin_id}", json={"role": "staff"}).status_code == 409
    assert client.patch(f"/api/users/{admin_id}", json={"active": False}).status_code == 409


def test_change_password_signs_out_other_sessions(client):
    with TestClient(app) as other:
        _as(other, "admin@test.local", "pw")
        assert other.get("/api/auth/me").status_code == 200
        bad = client.post("/api/auth/change-password", json={"current_password": "wrong", "new_password": "river-Lantern-47-moss"})
        assert bad.status_code == 422
        weak = client.post("/api/auth/change-password", json={"current_password": "pw", "new_password": "password"})
        assert weak.status_code == 422
        ok = client.post("/api/auth/change-password", json={"current_password": "pw", "new_password": "river-Lantern-47-moss"})
        assert ok.status_code == 200
        client.headers["Authorization"] = f"Bearer {ok.json()['token']}"  # this device stays signed in
        assert client.get("/api/auth/me").status_code == 200
        assert other.get("/api/auth/me").status_code == 401  # the other device is signed out
    assert _login(client, "admin@test.local", "pw").status_code == 401
    assert _login(client, "admin@test.local", "river-Lantern-47-moss").status_code == 200


def test_admin_can_reset_a_colleagues_password(client):
    uid = client.post("/api/users", json={"email": "bola@test.local", "password": "river-Lantern-47-moss"}).json()["id"]
    assert client.patch(f"/api/users/{uid}", json={"password": "short"}).status_code == 422
    assert client.patch(f"/api/users/{uid}", json={"password": "another-Quiet-52-harbour"}).status_code == 200
    assert _login(client, "bola@test.local", "river-Lantern-47-moss").status_code == 401
    assert _login(client, "bola@test.local", "another-Quiet-52-harbour").status_code == 200


def test_tampered_or_foreign_tokens_are_rejected(client):
    good = client.headers["Authorization"].split()[1]
    for token in (good[:-3] + "abc", "garbage", ""):
        assert TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_old_style_tokens_without_an_account_id_are_cleanly_refused(client):
    from datetime import UTC, datetime, timedelta

    import jwt

    s = get_settings()
    for claims in ({"sub": "admin@test.local"}, {"sub": "x", "uid": "1", "tv": 0}, {"sub": "x", "uid": 99999, "tv": 0}):
        token = jwt.encode({**claims, "exp": datetime.now(UTC) + timedelta(hours=1)}, s.jwt_secret, algorithm="HS256")
        r = TestClient(app).get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401, claims


def test_security_headers_and_hidden_docs(client):
    r = client.get("/healthz")
    h = {k.lower(): v for k, v in r.headers.items()}
    assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"] and "script-src 'self'" in h["content-security-policy"]
    assert "strict-transport-security" not in h  # plain http in tests
    https = client.get("/healthz", headers={"x-forwarded-proto": "https"})
    assert "strict-transport-security" in {k.lower() for k in https.headers}
    assert client.get("/api/stats").headers["cache-control"] == "no-store"
    assert client.get("/docs").status_code != 200 and client.get("/openapi.json").status_code != 200


def test_production_refuses_development_secrets():
    prod = Settings(database_url="postgresql://u:p@h/db", jwt_secret="dev-secret-change-me")
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        assert_safe_to_run(prod)
    with pytest.raises(RuntimeError):
        assert_safe_to_run(Settings(database_url="postgresql://u:p@h/db", jwt_secret="short"))
    assert_safe_to_run(Settings(database_url="postgresql://u:p@h/db", jwt_secret="x" * 40))
    assert_safe_to_run(Settings(database_url="sqlite:///./x.db"))  # local development is fine


def test_attachment_links_must_be_web_addresses(client):
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "ftp://x/y", "data:text/html,hi"):
        r = client.post("/api/campaigns", json={"name": "x", "body": "hi", "media_url": bad, "media_type": "image"})
        assert r.status_code == 422, bad
    ok = client.post("/api/campaigns", json={"name": "x", "body": "hi", "media_url": "https://example.com/a.jpg", "media_type": "image"})
    assert ok.status_code == 201
    assert client.post("/api/campaigns", json={"name": "x", "body": "hi", "wa_template_params": ["secret"]}).status_code == 422
    assert client.post("/api/campaigns", json={"name": "x", "body": "hi", "wa_template_name": "Bad Name!"}).status_code == 422


def test_csv_export_neutralises_spreadsheet_formulas(client):
    client.post("/api/contacts", json={"name": '=HYPERLINK("http://evil","x")', "phone": "08031111111", "notes": "@SUM(1)"})
    client.post("/api/contacts", json={"name": "Plain", "phone": "+2348032222222"})
    text = client.post("/api/contacts/export", json={}).text
    assert "'=HYPERLINK" in text and "'@SUM" in text
    assert "+2348031111111" in text and "'+2348031111111" not in text  # real numbers stay usable


def test_oversized_contact_fields_are_refused(client):
    r = client.post("/api/contacts", json={"name": "x" * 201, "phone": "08031111111"})
    assert r.status_code == 422 and "Name is too long" in str(r.json())
    assert client.post("/api/contacts", json={"name": "ok", "phone": "08031111111", "notes": "n" * 5001}).status_code == 422
