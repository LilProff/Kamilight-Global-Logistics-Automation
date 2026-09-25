"""Turns a filter spec (what staff pick in the filter builder) into a contact query.

Spec keys, all optional:
  search            text in name, phone, email, company
  statuses          ["dormant", "repeat"]
  customer_types    ["online_seller"]
  routes_any        ["china-air"]         contact uses at least one of these routes
  tags_any          ["festive-2025"]
  sources           ["referral"]
  cities            ["Lagos"]
  assigned_to       "Tunde"
  min_shipments / max_shipments
  min_spend / max_spend                    naira
  shipped_within_days                      last shipment in the last N days
  not_shipped_for_days                     last shipment more than N days ago (never-shipped excluded)
  never_shipped     true
  opted_in_only     true                   only contacts who agreed to WhatsApp marketing
"""

from datetime import timedelta

from sqlalchemy import Select, func, or_, select

from app.lists import slug
from app.models import Contact, utcnow

KNOWN_KEYS = {
    "search", "statuses", "customer_types", "routes_any", "tags_any", "sources", "cities", "assigned_to",
    "min_shipments", "max_shipments", "min_spend", "max_spend", "shipped_within_days",
    "not_shipped_for_days", "never_shipped", "opted_in_only",
}


def _list(spec: dict, key: str) -> list[str]:
    value = spec.get(key)
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return [str(v) for v in value if str(v).strip()]


def apply_filters(query: Select, spec: dict | None) -> Select:
    spec = spec or {}
    now = utcnow()

    if text := str(spec.get("search") or "").strip():
        like = f"%{text.lower()}%"
        query = query.where(
            or_(
                func.lower(Contact.name).like(like),
                func.lower(func.coalesce(Contact.email, "")).like(like),
                func.lower(Contact.company).like(like),
                func.coalesce(Contact.phone, "").like(f"%{text.lstrip('0')}%"),
            )
        )
    if statuses := _list(spec, "statuses"):
        query = query.where(Contact.status.in_(statuses))
    if types := _list(spec, "customer_types"):
        query = query.where(Contact.customer_type.in_(types))
    if sources := _list(spec, "sources"):
        query = query.where(Contact.source.in_(sources))
    if cities := _list(spec, "cities"):
        query = query.where(func.lower(Contact.city).in_([c.lower() for c in cities]))
    if routes := _list(spec, "routes_any"):
        query = query.where(or_(*[Contact.routes.like(f"%,{slug(r)},%") for r in routes]))
    if tags := _list(spec, "tags_any"):
        query = query.where(or_(*[Contact.tags.like(f"%,{slug(t)},%") for t in tags]))
    if assigned := str(spec.get("assigned_to") or "").strip():
        query = query.where(func.lower(Contact.assigned_to) == assigned.lower())

    if spec.get("min_shipments") not in (None, ""):
        query = query.where(Contact.shipments_count >= int(spec["min_shipments"]))
    if spec.get("max_shipments") not in (None, ""):
        query = query.where(Contact.shipments_count <= int(spec["max_shipments"]))
    if spec.get("min_spend") not in (None, ""):
        query = query.where(Contact.total_spend_ngn >= float(spec["min_spend"]))
    if spec.get("max_spend") not in (None, ""):
        query = query.where(Contact.total_spend_ngn <= float(spec["max_spend"]))

    if spec.get("shipped_within_days") not in (None, ""):
        query = query.where(Contact.last_shipment_at >= now - timedelta(days=int(spec["shipped_within_days"])))
    if spec.get("not_shipped_for_days") not in (None, ""):
        query = query.where(Contact.last_shipment_at < now - timedelta(days=int(spec["not_shipped_for_days"])))
    if spec.get("never_shipped"):
        query = query.where(Contact.shipments_count == 0)
    if spec.get("opted_in_only"):
        query = query.where(Contact.wa_opt_in.is_(True))
    return query


def contacts_query(spec: dict | None) -> Select:
    return apply_filters(select(Contact), spec)


def reachable(query: Select, channel: str, category: str) -> Select:
    """Narrow an audience to people we may actually message on this channel.

    Opt-outs and do-not-contact are always excluded. WhatsApp marketing also requires opt-in (Meta policy).
    """
    query = query.where(Contact.do_not_contact.is_(False))
    if channel == "whatsapp":
        query = query.where(Contact.phone.is_not(None), Contact.wa_opted_out.is_(False))
        if category == "marketing":
            query = query.where(Contact.wa_opt_in.is_(True))
    elif channel == "email":
        query = query.where(Contact.email.is_not(None), Contact.email != "")
    return query
