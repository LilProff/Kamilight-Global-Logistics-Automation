"""WhatsApp webhook events: delivery receipts, inbound replies, and STOP opt-outs."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CampaignRecipient, Contact, ContactEvent, utcnow
from app.phone import normalize_phone

STOP_WORDS = {"stop", "unsubscribe", "stop all", "opt out", "optout", "cancel"}
START_WORDS = {"start", "subscribe", "opt in", "optin"}
STATUS_RANK = {"queued": 0, "sent": 1, "delivered": 2, "read": 3}


def _message_text(msg: dict) -> str:
    kind = msg.get("type")
    if kind == "text":
        return msg.get("text", {}).get("body", "")
    if kind == "button":
        return msg.get("button", {}).get("text", "")
    if kind == "interactive":
        inter = msg.get("interactive", {})
        return (inter.get("button_reply") or inter.get("list_reply") or {}).get("title", "")
    return f"[{kind}]"


def handle_status(db: Session, st: dict) -> None:
    rec = db.scalar(select(CampaignRecipient).where(CampaignRecipient.provider_message_id == st.get("id")))
    if rec is None:
        return
    new, now = st.get("status"), utcnow()
    if new == "failed":
        errors = st.get("errors") or [{}]
        rec.status = "failed"
        rec.error = f"{errors[0].get('code', '')}: {errors[0].get('title', 'failed')}"[:500]
    elif new in STATUS_RANK and STATUS_RANK[new] > STATUS_RANK.get(rec.status, -1):
        rec.status = new  # receipts can arrive out of order; only move forward
        if new == "delivered":
            rec.delivered_at = rec.delivered_at or now
        if new == "read":
            rec.read_at = rec.read_at or now
            rec.delivered_at = rec.delivered_at or now


def handle_message(db: Session, msg: dict, profile_name: str = "") -> Contact | None:
    phone = normalize_phone("+" + str(msg.get("from", "")))
    if not phone:
        return None
    now = utcnow()
    contact = db.scalar(select(Contact).where(Contact.phone == phone))
    if contact is None:
        contact = Contact(name=profile_name, phone=phone, source="whatsapp", status="new")
        db.add(contact)
        db.flush()
        db.add(ContactEvent(contact_id=contact.id, kind="status", title="New enquiry on WhatsApp"))
    contact.last_inbound_at = now
    text = _message_text(msg)
    word = text.strip().lower()

    if word in STOP_WORDS:
        contact.wa_opted_out, contact.wa_opt_in = True, False
        db.add(ContactEvent(contact_id=contact.id, kind="opt_out", title="Opted out of WhatsApp messages", detail=text))
    elif word in START_WORDS:
        contact.wa_opted_out, contact.wa_opt_in, contact.wa_opt_in_at = False, True, now
        db.add(ContactEvent(contact_id=contact.id, kind="opt_in", title="Opted in to WhatsApp updates", detail=text))
    else:
        db.add(ContactEvent(contact_id=contact.id, kind="inbound", title="WhatsApp message", detail=text[:2000]))

    if word in STOP_WORDS:
        return contact  # an opt-out is not engagement; don't count it as a campaign reply

    # Credit the reply to the latest campaign this person received in the last 7 days
    rec = db.scalar(
        select(CampaignRecipient)
        .where(CampaignRecipient.contact_id == contact.id, CampaignRecipient.sent_at >= now - timedelta(days=7))
        .order_by(CampaignRecipient.sent_at.desc())
        .limit(1)
    )
    if rec is not None:
        rec.replied = True
    return contact


def handle_webhook(db: Session, payload: dict) -> dict:
    statuses = messages = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name", "") for c in value.get("contacts", [])}
            for st in value.get("statuses", []):
                handle_status(db, st)
                statuses += 1
            for msg in value.get("messages", []):
                handle_message(db, msg, names.get(msg.get("from"), ""))
                messages += 1
    db.commit()
    return {"statuses": statuses, "messages": messages}
