"""Campaign engine: audience preview, recipient snapshot, paced sending, reporting."""

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.filters import apply_filters, reachable
from app.messaging import Sender, channel_live, get_sender, render
from app.models import Campaign, CampaignRecipient, Contact, ContactEvent, Segment, utcnow


def fee_per_message(channel: str, category: str) -> float:
    if channel != "whatsapp":
        return 0.0
    s = get_settings()
    return s.wa_marketing_fee_ngn if category == "marketing" else s.wa_utility_fee_ngn


def campaign_filters(db: Session, campaign: Campaign) -> dict:
    """A campaign targets a saved segment, extra filters, or both (combined)."""
    spec: dict = {}
    if campaign.segment_id:
        seg = db.get(Segment, campaign.segment_id)
        if seg:
            spec |= seg.filters or {}
    spec |= {k: v for k, v in (campaign.filters or {}).items() if v not in (None, "", [])}
    return spec


def preview(db: Session, spec: dict, channel: str, category: str) -> dict:
    count = lambda q: db.scalar(select(func.count()).select_from(q.subquery()))  # noqa: E731
    base = apply_filters(select(Contact.id), spec)
    matched = count(base)
    blocked = count(base.where(Contact.do_not_contact.is_(True)))
    live = base.where(Contact.do_not_contact.is_(False))
    breakdown = {"do_not_contact": blocked}
    if channel == "whatsapp":
        breakdown["no_phone"] = count(live.where(Contact.phone.is_(None)))
        live = live.where(Contact.phone.is_not(None))
        breakdown["opted_out"] = count(live.where(Contact.wa_opted_out.is_(True)))
        live = live.where(Contact.wa_opted_out.is_(False))
        if category == "marketing":
            breakdown["no_marketing_consent"] = count(live.where(Contact.wa_opt_in.is_(False)))
    elif channel == "email":
        breakdown["no_email"] = count(live.where((Contact.email.is_(None)) | (Contact.email == "")))
    will_receive = count(reachable(apply_filters(select(Contact.id), spec), channel, category))
    fee = fee_per_message(channel, category)
    return {
        "matched": matched,
        "will_receive": will_receive,
        "excluded": breakdown,
        "fee_per_message_ngn": fee,
        "estimated_cost_ngn": round(will_receive * fee, 2),
        "test_mode": not channel_live(channel),
    }


def start(db: Session, campaign: Campaign) -> int:
    """Freeze the audience into recipients and switch the campaign to 'sending'. Returns recipient count."""
    spec = campaign_filters(db, campaign)
    contacts = db.scalars(reachable(apply_filters(select(Contact), spec), campaign.channel, campaign.category)).all()
    for c in contacts:
        db.add(CampaignRecipient(campaign_id=campaign.id, contact_id=c.id, rendered_body=render(campaign.body, c)))
    campaign.status = "sending" if contacts else "sent"
    campaign.started_at = utcnow()
    campaign.test_mode = not channel_live(campaign.channel)
    if not contacts:
        campaign.finished_at = campaign.started_at
    db.commit()
    return len(contacts)


def _still_reachable(contact: Contact, campaign: Campaign) -> str:
    """Re-check at send time: someone may have replied STOP after the campaign was queued."""
    if contact.do_not_contact:
        return "Marked do not contact"
    if campaign.channel == "whatsapp":
        if contact.wa_opted_out:
            return "Opted out"
        if campaign.category == "marketing" and not contact.wa_opt_in:
            return "No marketing consent"
    return ""


def process_batch(db: Session, limit: int, sender_for: Callable[[str], Sender] = get_sender) -> int:
    """Send up to `limit` queued messages across campaigns. Returns how many were attempted."""
    rows = db.scalars(
        select(CampaignRecipient)
        .join(Campaign)
        .where(Campaign.status == "sending", CampaignRecipient.status == "queued")
        .order_by(CampaignRecipient.id)
        .limit(limit)
    ).all()
    senders: dict[str, Sender] = {}
    touched: set[int] = set()
    for rec in rows:
        campaign, contact = rec.campaign, rec.contact
        touched.add(campaign.id)
        if reason := _still_reachable(contact, campaign):
            rec.status, rec.error = "skipped", reason
            continue
        sender = senders.setdefault(campaign.channel, sender_for(campaign.channel))
        result = sender.send(contact, campaign, rec.rendered_body)
        if result.ok:
            rec.status, rec.provider_message_id, rec.sent_at = "sent", result.message_id, utcnow()
            db.add(ContactEvent(
                contact_id=contact.id, kind="campaign",
                title=f"Campaign sent: {campaign.name}" + (" (test mode)" if sender.test_mode else ""),
                detail=rec.rendered_body[:500],
            ))
        else:
            rec.status, rec.error = "failed", result.error
    db.flush()
    for campaign_id in touched:
        remaining = db.scalar(
            select(func.count()).where(CampaignRecipient.campaign_id == campaign_id, CampaignRecipient.status == "queued")
        )
        if remaining == 0:
            campaign = db.get(Campaign, campaign_id)
            campaign.status, campaign.finished_at = "sent", utcnow()
    db.commit()
    return len(rows)


def start_due(db: Session) -> int:
    due = db.scalars(select(Campaign).where(Campaign.status == "scheduled", Campaign.scheduled_at <= utcnow())).all()
    for campaign in due:
        start(db, campaign)
    return len(due)


def report(db: Session, campaign: Campaign) -> dict:
    counts = dict(
        db.execute(
            select(CampaignRecipient.status, func.count())
            .where(CampaignRecipient.campaign_id == campaign.id)
            .group_by(CampaignRecipient.status)
        ).all()
    )
    replied = db.scalar(
        select(func.count()).where(CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.replied.is_(True))
    )
    total = sum(counts.values())
    reached = counts.get("sent", 0) + counts.get("delivered", 0) + counts.get("read", 0)
    delivered = counts.get("delivered", 0) + counts.get("read", 0)
    # Meta bills per delivered message; before delivery receipts arrive, count sent as the upper bound
    billable = delivered if delivered else reached
    return {
        "total": total,
        "queued": counts.get("queued", 0),
        "sent": reached,
        "delivered": delivered,
        "read": counts.get("read", 0),
        "failed": counts.get("failed", 0),
        "skipped": counts.get("skipped", 0),
        "replied": replied,
        "estimated_cost_ngn": 0 if campaign.test_mode else round(billable * fee_per_message(campaign.channel, campaign.category), 2),
    }
