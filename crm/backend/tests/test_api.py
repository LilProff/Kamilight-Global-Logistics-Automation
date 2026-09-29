from app.campaigns import process_batch
from app.db import SessionLocal


def _contact(client, **kw):
    r = client.post("/api/contacts", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def _drain():
    with SessionLocal() as db:
        while process_batch(db, limit=50):
            pass


def test_health_endpoints(client):
    assert client.get("/health").json() == {"ok": True}
    assert client.get("/health/db").json() == {"ok": True}


def test_postgres_tables_are_locked_down_from_the_public_api():
    import pytest
    from sqlalchemy import text

    from app.db import engine, harden_postgres

    if engine.dialect.name != "postgresql":
        pytest.skip("Postgres only (run with TEST_DATABASE_URL)")
    harden_postgres(engine)
    with engine.connect() as conn:
        rls = dict(conn.execute(text(
            "select relname, relrowsecurity from pg_class c join pg_namespace n on n.oid = c.relnamespace "
            "where n.nspname = 'public' and relkind = 'r'")).all())
    assert rls and all(rls.values()), rls


def test_requires_login():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anon:
        assert anon.post("/api/contacts/search", json={}).status_code == 401
        assert anon.post("/api/auth/login", json={"email": "admin@test.local", "password": "nope"}).status_code == 401


def test_contact_crud_and_validation(client):
    c = _contact(client, name="Ada", phone="0803 111 1111", routes=["China Air"], wa_opt_in=True)
    assert c["phone"] == "+2348031111111" and c["routes"] == ["china-air"] and c["wa_opt_in_at"]
    assert client.post("/api/contacts", json={"name": "Dup", "phone": "+2348031111111"}).status_code == 409
    assert client.post("/api/contacts", json={"name": "Bad", "phone": "123"}).status_code == 422
    assert client.post("/api/contacts", json={"name": "Nothing"}).status_code == 422

    r = client.patch(f"/api/contacts/{c['id']}", json={"status": "lost", "lost_reason": "Price", "tags": ["VIP Lead"]})
    assert r.json()["status"] == "lost" and r.json()["tags"] == ["vip-lead"]
    client.post(f"/api/contacts/{c['id']}/shipments", json={"amount_ngn": 120000, "route": "china-air"})
    d = client.get(f"/api/contacts/{c['id']}").json()
    assert d["status"] == "booked" and d["shipments_count"] == 1
    assert [e["kind"] for e in d["events"]][:2] == ["status", "shipment"]

    page = client.post("/api/contacts/search", json={"filters": {"statuses": ["booked"]}}).json()
    assert page["total"] == 1
    assert "china-air" in client.get("/api/contacts/options").json()["routes"]


def test_segment_counts(client):
    _contact(client, name="A", phone="08031111111", customer_type="online_seller")
    _contact(client, name="B", phone="08032222222")
    seg = client.post("/api/segments", json={"name": "Sellers", "filters": {"customer_types": ["online_seller"]}}).json()
    assert seg["count"] == 1
    assert client.post("/api/segments", json={"name": "Sellers"}).status_code == 409


def test_campaign_end_to_end(client):
    a = _contact(client, name="Ada Obi", phone="08031111111", city="Ikeja", wa_opt_in=True, routes=["china-air"])
    _contact(client, name="Bayo", phone="08032222222", wa_opt_in=False, routes=["china-air"])  # no marketing consent
    _contact(client, name="Chi", phone="08033333333", wa_opt_in=True, do_not_contact=True, routes=["china-air"])
    _contact(client, name="Email only", email="e@x.com", wa_opt_in=True, routes=["china-air"])

    spec = {"routes_any": ["china-air"]}
    p = client.post("/api/campaigns/preview", json={"filters": spec, "channel": "whatsapp", "category": "marketing"}).json()
    assert p["matched"] == 4 and p["will_receive"] == 1 and p["estimated_cost_ngn"] == 84 and p["test_mode"]
    assert p["excluded"] == {"do_not_contact": 1, "no_phone": 1, "opted_out": 0, "no_marketing_consent": 1}

    utility = client.post("/api/campaigns/preview", json={"filters": spec, "category": "utility"}).json()
    assert utility["will_receive"] == 2 and utility["estimated_cost_ngn"] == 28

    assert client.post("/api/campaigns", json={"name": "Empty", "filters": spec}).status_code == 422
    camp = client.post("/api/campaigns", json={
        "name": "Friday cut-off", "filters": spec, "body": "Hi {first_name}, China air closes Friday. {city} pickup free.",
    }).json()
    sent = client.post(f"/api/campaigns/{camp['id']}/send", json={}).json()
    assert sent["status"] == "sending" and sent["test_mode"] and sent["report"]["queued"] == 1
    _drain()
    done = client.get(f"/api/campaigns/{camp['id']}").json()
    assert done["status"] == "sent" and done["report"]["sent"] == 1 and done["report"]["estimated_cost_ngn"] == 0
    rec = client.get(f"/api/campaigns/{camp['id']}/recipients").json()[0]
    assert rec["name"] == "Ada Obi"
    timeline = client.get(f"/api/contacts/{a['id']}").json()["events"]
    assert timeline[0]["kind"] == "campaign" and "Hi Ada, China air closes Friday. Ikeja pickup free." in timeline[0]["detail"]

    assert client.put(f"/api/campaigns/{camp['id']}", json={"name": "x", "body": "y"}).status_code == 409
    copy = client.post(f"/api/campaigns/{camp['id']}/duplicate").json()
    assert copy["status"] == "draft" and copy["name"].endswith("(copy)")


def test_scheduled_campaign_and_cancel(client):
    _contact(client, name="Ada", phone="08031111111", wa_opt_in=True)
    camp = client.post("/api/campaigns", json={"name": "Later", "body": "Hi"}).json()
    r = client.post(f"/api/campaigns/{camp['id']}/send", json={"send_at": "2099-01-01T09:00:00"}).json()
    assert r["status"] == "scheduled" and r["audience"]["will_receive"] == 1
    assert client.post(f"/api/campaigns/{camp['id']}/cancel").json()["status"] == "cancelled"


def _wa(value):
    return {"entry": [{"changes": [{"value": value}]}]}


def test_webhook_receipts_replies_and_stop(client):
    a = _contact(client, name="Ada", phone="08031111111", wa_opt_in=True)
    camp = client.post("/api/campaigns", json={"name": "Promo", "body": "Hi"}).json()
    client.post(f"/api/campaigns/{camp['id']}/send", json={})
    _drain()
    from app.models import CampaignRecipient

    with SessionLocal() as db:
        msg_id = db.query(CampaignRecipient).one().provider_message_id

    client.post("/api/webhooks/whatsapp", json=_wa({"statuses": [{"id": msg_id, "status": "read"}]}))
    client.post("/api/webhooks/whatsapp", json=_wa({"statuses": [{"id": msg_id, "status": "delivered"}]}))  # late, ignored
    client.post("/api/webhooks/whatsapp", json=_wa({
        "contacts": [{"wa_id": "2348031111111", "profile": {"name": "Ada"}}],
        "messages": [{"from": "2348031111111", "type": "text", "text": {"body": "How much per kg?"}}],
    }))
    report = client.get(f"/api/campaigns/{camp['id']}").json()["report"]
    assert report["read"] == 1 and report["delivered"] == 1 and report["replied"] == 1

    b = _contact(client, name="Bola", phone="08032222222", wa_opt_in=True)
    camp2 = client.post("/api/campaigns", json={"name": "Promo 2", "body": "Hi", "filters": {"search": "Bola"}}).json()
    client.post(f"/api/campaigns/{camp2['id']}/send", json={})
    _drain()
    client.post("/api/webhooks/whatsapp", json=_wa({"messages": [{"from": "2348032222222", "type": "text", "text": {"body": " STOP "}}]}))
    assert client.get(f"/api/campaigns/{camp2['id']}").json()["report"]["replied"] == 0  # opt-out isn't a reply
    assert client.get(f"/api/contacts/{b['id']}").json()["wa_opted_out"]

    client.post("/api/webhooks/whatsapp", json=_wa({"messages": [{"from": "2348031111111", "type": "text", "text": {"body": " STOP "}}]}))
    contact = client.get(f"/api/contacts/{a['id']}").json()
    assert contact["wa_opted_out"] and not contact["wa_opt_in"]
    p = client.post("/api/campaigns/preview", json={"filters": {}, "category": "utility"}).json()
    assert p["will_receive"] == 0 and p["excluded"]["opted_out"] == 2

    # A brand-new number writing in becomes a new enquiry
    client.post("/api/webhooks/whatsapp", json=_wa({
        "contacts": [{"wa_id": "2348099999999", "profile": {"name": "New Buyer"}}],
        "messages": [{"from": "2348099999999", "type": "text", "text": {"body": "Hello, do you ship from China?"}}],
    }))
    page = client.post("/api/contacts/search", json={"filters": {"sources": ["whatsapp"]}}).json()
    assert page["total"] == 1 and page["items"][0]["name"] == "New Buyer"


def test_webhook_verify(client):
    ok = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "kgl-verify", "hub.challenge": "42"})
    assert ok.status_code == 200 and ok.text == "42"
    bad = client.get("/api/webhooks/whatsapp", params={"hub.mode": "subscribe", "hub.verify_token": "x", "hub.challenge": "42"})
    assert bad.status_code == 403


def test_import_endpoint(client):
    csv = b"Name,Phone,Tag\nAda,08031111111,existing client\nBad,123,\n"
    r = client.post("/api/contacts/import", files={"file": ("list.csv", csv, "text/csv")}, data={"opt_in": "true"}).json()
    assert r["created"] == 1 and r["skipped"] == 1
    assert client.get("/api/stats").json()["marketing_consent"] == 1
