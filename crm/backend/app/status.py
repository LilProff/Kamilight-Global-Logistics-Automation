"""Automatic customer statuses: statuses follow real activity, staff can still override by hand."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.lists import merge, slug
from app.models import Contact, ContactEvent, utcnow

SHIPPED_STATUSES = {"booked", "repeat", "vip"}


def status_from_activity(contact: Contact, now: datetime | None = None) -> str:
    """What the status should be, given shipments and spend. Never-shipped contacts keep new/quoted/lost."""
    s = get_settings()
    now = now or utcnow()
    if contact.shipments_count <= 0:
        return contact.status if contact.status in {"new", "quoted", "lost"} else "new"
    if contact.last_shipment_at and contact.last_shipment_at < now - timedelta(days=s.dormant_after_days):
        return "dormant"
    if contact.shipments_count >= s.vip_min_shipments or contact.total_spend_ngn >= s.vip_min_spend_ngn:
        return "vip"
    if contact.shipments_count >= 2:
        return "repeat"
    return "booked"


def set_status(db: Session, contact: Contact, new_status: str, reason: str) -> None:
    if contact.status == new_status:
        return
    old = contact.status
    contact.status = new_status
    db.add(ContactEvent(contact_id=contact.id, kind="status", title=f"Status: {old} → {new_status}", detail=reason))


def record_shipment(
    db: Session, contact: Contact, amount_ngn: float, route: str = "", note: str = "", when: datetime | None = None
) -> None:
    when = when or utcnow()
    contact.shipments_count += 1
    contact.total_spend_ngn += max(amount_ngn, 0)
    contact.first_shipment_at = contact.first_shipment_at or when
    if not contact.last_shipment_at or when >= contact.last_shipment_at:
        contact.last_shipment_at = when
        if route:
            contact.last_route = slug(route)
    if route:
        contact.routes = merge(contact.routes, [route])
    db.add(
        ContactEvent(
            contact_id=contact.id, kind="shipment", title=f"Shipment{' · ' + route if route else ''}",
            detail=note, amount_ngn=amount_ngn, created_at=when,
        )
    )
    set_status(db, contact, status_from_activity(contact), "Shipment recorded")


def mark_quoted(db: Session, contact: Contact, detail: str = "") -> None:
    db.add(ContactEvent(contact_id=contact.id, kind="quote", title="Quote sent", detail=detail))
    if contact.status in {"new", "lost"}:
        set_status(db, contact, "quoted", "Quote sent")


def sweep_dormant(db: Session) -> int:
    """Daily: shipped customers silent for N days become dormant. Returns how many changed."""
    s = get_settings()
    cutoff = utcnow() - timedelta(days=s.dormant_after_days)
    ids = db.scalars(
        select(Contact.id).where(Contact.status.in_(SHIPPED_STATUSES), Contact.last_shipment_at < cutoff)
    ).all()
    if not ids:
        return 0
    db.execute(update(Contact).where(Contact.id.in_(ids)).values(status="dormant"))
    db.add_all(
        ContactEvent(contact_id=i, kind="status", title="Status: → dormant", detail=f"No shipment in {s.dormant_after_days} days")
        for i in ids
    )
    db.commit()
    return len(ids)
