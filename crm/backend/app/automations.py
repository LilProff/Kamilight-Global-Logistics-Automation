"""Automatic campaigns: win-back, quote follow-up and welcome.

Each rule is OFF until staff switch it on. When on, a background pass (every few minutes, only during local
daytime hours) finds who qualifies, caps the batch at a daily limit that protects the WhatsApp number's rating,
and queues the messages through the normal campaign engine, so consent checks, opt-outs, delivery tracking,
reports and test mode all behave exactly like a hand-made campaign. Nobody is messaged twice within a rule's
cool-down.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.campaigns import fee_per_message
from app.config import get_settings
from app.filters import reachable
from app.messaging import channel_live, render
from app.models import Automation, AutomationLog, Campaign, CampaignRecipient, Contact, ContactEvent, utcnow


@dataclass(frozen=True)
class Rule:
    key: str
    title: str
    summary: str
    category: str  # marketing or utility (Meta pricing and consent rules)
    uses_days: bool
    days: int
    cooldown_days: int
    daily_limit: int
    body: str


RULES: dict[str, Rule] = {
    "winback": Rule(
        key="winback",
        title="Win back past customers",
        summary="Messages customers who have gone quiet (status Dormant) and agreed to receive offers, then leaves them alone for the cool-down.",
        category="marketing", uses_days=False, days=0, cooldown_days=60, daily_limit=30,
        body=("Hi {first_name}, it's been a while since your last shipment with Kamilight Global Logistics. "
              "Our air and sea consolidations to and from Nigeria are open and we'd love to have you back. "
              "Reply QUOTE for a price in 1 minute. Reply STOP to opt out."),
    ),
    "quote_followup": Rule(
        key="quote_followup",
        title="Follow up on quotes",
        summary="Checks in with customers who were quoted but haven't booked, a few days after the quote.",
        category="utility", uses_days=True, days=2, cooldown_days=14, daily_limit=50,
        body=("Hi {first_name}, just checking in on the quote we sent. Would you like us to book your shipment? "
              "Reply YES and we'll arrange it, or tell us if anything needs changing."),
    ),
    "welcome": Rule(
        key="welcome",
        title="Welcome new enquiries",
        summary="Greets people who message KGL's WhatsApp for the first time, once.",
        category="utility", uses_days=False, days=0, cooldown_days=3650, daily_limit=100,
        body=("Hi {first_name}, thanks for contacting Kamilight Global Logistics! We ship by air and sea to and from Nigeria. "
              "Tell us where from and to, the weight and what you're sending, and we'll send you a price."),
    ),
}


def ensure_automations(db: Session) -> None:
    """Create the three rules (switched off) on first start."""
    have = set(db.scalars(select(Automation.key)))
    for rule in RULES.values():
        if rule.key not in have:
            db.add(Automation(key=rule.key, enabled=False, body=rule.body, days=rule.days,
                              cooldown_days=rule.cooldown_days, daily_limit=rule.daily_limit))
    db.commit()


def local_now(now: datetime | None = None) -> datetime:
    return (now or utcnow()) + timedelta(hours=get_settings().local_utc_offset_hours)


def in_sending_hours(now: datetime | None = None) -> bool:
    s = get_settings()
    return s.automation_hours_start <= local_now(now).hour < s.automation_hours_end


def local_midnight_utc(now: datetime | None = None) -> datetime:
    local = local_now(now)
    return local.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=get_settings().local_utc_offset_hours)


def blocked_reason(auto: Automation) -> str | None:
    """Why this rule can't send right now, in plain words (None = fine)."""
    rule = RULES[auto.key]
    if not auto.body.strip() and not auto.wa_template_name:
        return "Write the message first."
    if channel_live("whatsapp") and rule.category == "marketing" and not auto.wa_template_name:
        return "WhatsApp only delivers marketing messages that use an approved template. Add the template name."
    return None


def eligible_query(auto: Automation, now: datetime | None = None) -> Select:
    """Everyone who currently qualifies and may be messaged (consent and opt-outs applied), before the cool-down."""
    now = now or utcnow()
    rule = RULES[auto.key]
    q = select(Contact)
    if auto.key == "winback":
        q = q.where(Contact.status == "dormant")
    elif auto.key == "quote_followup":
        last_quote = (
            select(func.max(ContactEvent.created_at)).where(ContactEvent.contact_id == Contact.id, ContactEvent.kind == "quote").scalar_subquery()
        )
        q = q.where(Contact.status == "quoted", last_quote <= now - timedelta(days=max(auto.days, 0)), last_quote >= now - timedelta(days=45))
    elif auto.key == "welcome":
        q = q.where(Contact.source == "whatsapp", Contact.status == "new", Contact.created_at >= now - timedelta(hours=24), Contact.last_inbound_at.is_not(None))
    return reachable(q, "whatsapp", rule.category)


def _cooldown_filter(q: Select, auto: Automation, now: datetime) -> Select:
    since = now - timedelta(days=max(auto.cooldown_days, 1))
    messaged = select(AutomationLog.contact_id).where(AutomationLog.automation_key == auto.key, AutomationLog.at >= since)
    return q.where(Contact.id.not_in(messaged))


def sent_today(db: Session, auto: Automation, now: datetime) -> int:
    return db.scalar(select(func.count()).select_from(AutomationLog).where(
        AutomationLog.automation_key == auto.key, AutomationLog.at >= local_midnight_utc(now))) or 0


def preview(db: Session, auto: Automation) -> dict:
    now = utcnow()
    rule = RULES[auto.key]
    qualifies = db.scalar(select(func.count()).select_from(_cooldown_filter(eligible_query(auto, now), auto, now).subquery()))
    today = sent_today(db, auto, now)
    return {
        "qualifies_now": qualifies,
        "sent_today": today,
        "daily_limit": auto.daily_limit,
        "next_batch": max(0, min(qualifies, auto.daily_limit - today)),
        "fee_per_message_ngn": fee_per_message("whatsapp", rule.category),
        "estimated_cost_ngn": round(min(qualifies, auto.daily_limit) * fee_per_message("whatsapp", rule.category), 2),
        "blocked_reason": blocked_reason(auto),
        "test_mode": not channel_live("whatsapp"),
    }


def run_automations(db: Session, now: datetime | None = None) -> int:
    """One pass over every enabled rule. Returns how many messages were queued."""
    now = now or utcnow()
    if not in_sending_hours(now):
        return 0
    queued = 0
    for auto in db.scalars(select(Automation).where(Automation.enabled.is_(True))).all():
        if blocked_reason(auto):
            continue
        remaining = auto.daily_limit - sent_today(db, auto, now)
        if remaining <= 0:
            continue
        rule = RULES[auto.key]
        contacts = db.scalars(_cooldown_filter(eligible_query(auto, now), auto, now).order_by(Contact.id).limit(remaining)).all()
        if not contacts:
            continue
        day = local_now(now).strftime("%d %b %Y")
        name = f"Auto: {rule.title} ({day})"
        campaign = db.scalar(select(Campaign).where(Campaign.name == name))  # one campaign per rule per day, so reports stay tidy
        if campaign is None:
            campaign = Campaign(
                name=name, channel="whatsapp", category=rule.category, body=auto.body, wa_template_name=auto.wa_template_name,
                wa_template_lang=auto.wa_template_lang, wa_template_params=list(auto.wa_template_params or []),
                status="sending", started_at=now, test_mode=not channel_live("whatsapp"),
            )
            db.add(campaign)
            db.flush()
        else:
            campaign.status, campaign.finished_at = "sending", None
        for c in contacts:
            db.add(CampaignRecipient(campaign_id=campaign.id, contact_id=c.id, rendered_body=render(auto.body, c)))
            db.add(AutomationLog(automation_key=auto.key, contact_id=c.id, campaign_id=campaign.id, at=now))
            queued += 1
        db.commit()
    return queued
