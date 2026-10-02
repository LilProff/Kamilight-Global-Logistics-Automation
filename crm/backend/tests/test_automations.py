from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.automations import ensure_automations, in_sending_hours, run_automations
from app.campaigns import process_batch
from app.config import get_settings
from app.models import Automation, AutomationLog, Campaign, CampaignRecipient, Contact, ContactEvent

NOON = datetime(2026, 10, 5, 11, 0)  # 12:00 in Lagos (UTC+1): inside sending hours
NIGHT = datetime(2026, 10, 5, 22, 0)  # 23:00 in Lagos: quiet hours


@pytest.fixture
def auto(db):
    ensure_automations(db)
    return lambda key: db.get(Automation, key)


def _on(db, auto, key, **changes):
    a = auto(key)
    a.enabled = True
    for k, v in changes.items():
        setattr(a, k, v)
    db.commit()


def _dormant(db, n, opted=True, **kw):
    cs = [Contact(name=f"Past Customer{i}", phone=f"+23480300000{i:02d}", status="dormant", wa_opt_in=opted, **kw) for i in range(n)]
    db.add_all(cs)
    db.commit()
    return cs


def test_three_rules_exist_and_start_switched_off(db, auto):
    assert {a.key: a.enabled for a in db.scalars(select(Automation))} == {"winback": False, "quote_followup": False, "welcome": False}
    ensure_automations(db)  # idempotent
    assert db.scalar(select(func.count()).select_from(Automation)) == 3


def test_nothing_is_sent_while_a_rule_is_off(db, auto):
    _dormant(db, 3)
    assert run_automations(db, NOON) == 0 and db.scalar(select(func.count()).select_from(Campaign)) == 0


def test_winback_messages_only_consenting_dormant_customers_once(db, auto):
    _dormant(db, 3)
    _dormant_no_consent = Contact(name="No Consent", phone="+2348039999999", status="dormant", wa_opt_in=False)
    stopped = Contact(name="Stopped", phone="+2348038888888", status="dormant", wa_opt_in=True, wa_opted_out=True)
    dnc = Contact(name="DNC", phone="+2348037777777", status="dormant", wa_opt_in=True, do_not_contact=True)
    active = Contact(name="Still Shipping", phone="+2348036666666", status="repeat", wa_opt_in=True)
    db.add_all([_dormant_no_consent, stopped, dnc, active])
    db.commit()
    _on(db, auto, "winback")

    assert run_automations(db, NOON) == 3  # only the three who qualify and agreed
    camp = db.scalar(select(Campaign))
    assert camp.name.startswith("Auto: Win back past customers") and camp.category == "marketing" and camp.test_mode
    recipients = db.scalars(select(CampaignRecipient)).all()
    assert len(recipients) == 3 and all("Hi Past" in r.rendered_body for r in recipients)
    # nobody is messaged twice: a second pass finds no one new
    assert run_automations(db, NOON + timedelta(minutes=5)) == 0
    assert db.scalar(select(func.count()).select_from(AutomationLog)) == 3
    # the normal sender delivers them (in test mode nothing really leaves)
    while process_batch(db, 50):
        pass
    assert {r.status for r in db.scalars(select(CampaignRecipient))} == {"sent"}


def test_cooldown_lets_someone_be_messaged_again_later(db, auto):
    _dormant(db, 1)
    _on(db, auto, "winback", cooldown_days=30)
    assert run_automations(db, NOON) == 1
    assert run_automations(db, NOON + timedelta(days=29)) == 0
    assert run_automations(db, NOON + timedelta(days=31)) == 1


def test_daily_limit_spreads_the_audience_over_days(db, auto):
    _dormant(db, 5)
    _on(db, auto, "winback", daily_limit=2)
    assert run_automations(db, NOON) == 2
    assert run_automations(db, NOON + timedelta(minutes=5)) == 0  # today's limit used up
    assert run_automations(db, NOON + timedelta(days=1)) == 2
    # one tidy campaign per day, not one per pass
    assert db.scalar(select(func.count()).select_from(Campaign)) == 2


def test_quiet_hours_send_nothing(db, auto):
    assert in_sending_hours(NOON) and not in_sending_hours(NIGHT)
    _dormant(db, 2)
    _on(db, auto, "winback")
    assert run_automations(db, NIGHT) == 0
    assert run_automations(db, NOON) == 2


def test_quote_followup_waits_the_chosen_days_and_skips_booked_customers(db, auto):
    old = NOON - timedelta(days=3)
    fresh = NOON - timedelta(hours=5)
    waiting = Contact(name="Waiting", phone="+2348031000001", status="quoted")
    recent = Contact(name="Recent", phone="+2348031000002", status="quoted")
    booked = Contact(name="Booked", phone="+2348031000003", status="booked")
    db.add_all([waiting, recent, booked])
    db.flush()
    db.add_all([
        ContactEvent(contact_id=waiting.id, kind="quote", title="Quote sent", created_at=old),
        ContactEvent(contact_id=recent.id, kind="quote", title="Quote sent", created_at=fresh),
        ContactEvent(contact_id=booked.id, kind="quote", title="Quote sent", created_at=old),
    ])
    db.commit()
    _on(db, auto, "quote_followup", days=2)
    assert run_automations(db, NOON) == 1
    assert db.scalar(select(Contact.name).join(CampaignRecipient, CampaignRecipient.contact_id == Contact.id)) == "Waiting"
    assert db.scalar(select(Campaign.category)) == "utility"  # follow-ups are service messages, no marketing consent needed


def test_welcome_greets_new_whatsapp_enquiries_once(db, auto):
    new = Contact(name="Fresh Lead", phone="+2348032000001", status="new", source="whatsapp", created_at=NOON - timedelta(hours=1), last_inbound_at=NOON - timedelta(minutes=50))
    old = Contact(name="Old Lead", phone="+2348032000002", status="new", source="whatsapp", created_at=NOON - timedelta(days=3), last_inbound_at=NOON - timedelta(days=3))
    imported = Contact(name="Imported", phone="+2348032000003", status="new", source="old_list", created_at=NOON - timedelta(hours=1))
    db.add_all([new, old, imported])
    db.commit()
    _on(db, auto, "welcome")
    assert run_automations(db, NOON) == 1
    assert run_automations(db, NOON + timedelta(hours=1)) == 0


def test_live_whatsapp_blocks_marketing_without_an_approved_template(db, auto, monkeypatch):
    monkeypatch.setattr(get_settings(), "wa_token", "live-token")
    monkeypatch.setattr(get_settings(), "wa_phone_number_id", "123")
    _dormant(db, 2)
    a = auto("winback")
    a.enabled = True
    db.commit()
    assert run_automations(db, NOON) == 0  # refuses to send free-form marketing Meta would reject
    a.wa_template_name = "winback_offer"
    db.commit()
    assert run_automations(db, NOON) == 2


def test_automations_api_preview_update_and_validation(client):
    items = {a["key"]: a for a in client.get("/api/automations").json()}
    assert set(items) == {"winback", "quote_followup", "welcome"} and not any(a["enabled"] for a in items.values())
    assert items["winback"]["category"] == "marketing" and items["quote_followup"]["uses_days"]

    for i in range(4):
        client.post("/api/contacts", json={"name": f"Gone{i}", "phone": f"0803111000{i}", "status": "dormant", "wa_opt_in": i < 3})
    pv = client.get("/api/automations").json()
    winback = next(a for a in pv if a["key"] == "winback")["preview"]
    assert winback["qualifies_now"] == 3 and winback["estimated_cost_ngn"] == 3 * 84 and winback["test_mode"]

    payload = {"enabled": True, "body": "Hi {first_name}, come back!", "days": 0, "cooldown_days": 45, "daily_limit": 10}
    updated = client.put("/api/automations/winback", json=payload).json()
    assert updated["enabled"] and updated["cooldown_days"] == 45 and updated["daily_limit"] == 10
    assert client.put("/api/automations/winback", json={**payload, "body": ""}).status_code == 422  # can't enable with no message
    assert client.put("/api/automations/winback", json={**payload, "daily_limit": 0}).status_code == 422
    assert client.put("/api/automations/winback", json={**payload, "wa_template_params": ["nope"]}).status_code == 422
    assert client.put("/api/automations/unknown", json=payload).status_code == 404
