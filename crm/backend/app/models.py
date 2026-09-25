from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    """Naive UTC, so SQLite and Postgres compare the same way."""
    return datetime.now(UTC).replace(tzinfo=None)


# The customer's journey with KGL. Order matters for display.
STATUSES = ["new", "quoted", "booked", "repeat", "vip", "dormant", "lost"]
CUSTOMER_TYPES = ["individual", "online_seller", "business", "diaspora", "partner"]
SOURCES = ["old_list", "whatsapp", "ad", "referral", "partner", "walk_in", "website", "apollo", "manual"]


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, index=True)  # E.164, e.g. +2348012345678
    email: Mapped[str | None] = mapped_column(String(200), index=True)
    company: Mapped[str] = mapped_column(String(200), default="")
    city: Mapped[str] = mapped_column(String(120), default="", index=True)
    customer_type: Mapped[str] = mapped_column(String(30), default="individual", index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    lost_reason: Mapped[str] = mapped_column(String(300), default="")
    source: Mapped[str] = mapped_column(String(30), default="manual", index=True)

    # Comma-wrapped slug lists (",china-air,lagos-uk,") so "contains" filters work the same on SQLite and Postgres
    routes: Mapped[str] = mapped_column(String(500), default="")
    tags: Mapped[str] = mapped_column(String(500), default="")
    goods: Mapped[str] = mapped_column(String(300), default="")
    preferred_mode: Mapped[str] = mapped_column(String(10), default="")  # air / sea / both

    shipments_count: Mapped[int] = mapped_column(Integer, default=0)
    total_spend_ngn: Mapped[float] = mapped_column(Float, default=0.0)
    first_shipment_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_shipment_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    last_route: Mapped[str] = mapped_column(String(60), default="")

    # Consent: marketing on WhatsApp only with opt-in; STOP sets opted_out and it is never undone automatically
    wa_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    wa_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime)
    wa_opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)  # opens WhatsApp's 24h service window

    assigned_to: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    next_follow_up: Mapped[datetime | None] = mapped_column(DateTime)
    birthday: Mapped[str] = mapped_column(String(5), default="")  # MM-DD

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    events: Mapped[list["ContactEvent"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", order_by="desc(ContactEvent.created_at)"
    )

    @property
    def route_list(self) -> list[str]:
        return [r for r in self.routes.split(",") if r]

    @property
    def tag_list(self) -> list[str]:
        return [t for t in self.tags.split(",") if t]

    @property
    def first_name(self) -> str:
        return (self.name or "").strip().split(" ")[0] if self.name else ""


class ContactEvent(Base):
    """One line on a customer's timeline: messages, campaigns, shipments, status changes, notes."""

    __tablename__ = "contact_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # inbound, outbound, campaign, shipment, status, note, import, opt_out
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    amount_ngn: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    contact: Mapped[Contact] = relationship(back_populates="events")


class Segment(Base):
    """A saved filter, e.g. 'China importers dormant 60+ days'."""

    __tablename__ = "segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    description: Mapped[str] = mapped_column(String(300), default="")
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


CAMPAIGN_STATUSES = ["draft", "scheduled", "sending", "sent", "cancelled"]
RECIPIENT_STATUSES = ["queued", "sent", "delivered", "read", "failed", "skipped"]


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20), default="whatsapp")  # whatsapp / email
    category: Mapped[str] = mapped_column(String(20), default="marketing")  # marketing / utility (Meta pricing)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)

    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    segment_id: Mapped[int | None] = mapped_column(ForeignKey("segments.id", ondelete="SET NULL"))

    # Message. WhatsApp outside the 24h window needs an approved template (wa_template_name).
    subject: Mapped[str] = mapped_column(String(200), default="")  # email only
    body: Mapped[str] = mapped_column(Text, default="")  # supports {first_name} {name} {city} {company} {last_route}
    media_url: Mapped[str] = mapped_column(String(500), default="")
    media_type: Mapped[str] = mapped_column(String(20), default="")  # image / video / document
    wa_template_name: Mapped[str] = mapped_column(String(120), default="")
    wa_template_lang: Mapped[str] = mapped_column(String(10), default="en")
    wa_template_params: Mapped[list] = mapped_column(JSON, default=list)  # e.g. ["first_name", "city"]

    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    test_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    recipients: Mapped[list["CampaignRecipient"]] = relationship(back_populates="campaign", cascade="all, delete-orphan")


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    rendered_body: Mapped[str] = mapped_column(Text, default="")
    provider_message_id: Mapped[str | None] = mapped_column(String(120), index=True)
    error: Mapped[str] = mapped_column(String(500), default="")
    replied: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    read_at: Mapped[datetime | None] = mapped_column(DateTime)

    campaign: Mapped[Campaign] = relationship(back_populates="recipients")
    contact: Mapped[Contact] = relationship()
