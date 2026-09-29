"""Import KGL's customer lists (Excel or CSV) into the database.

Column names are matched loosely ("Phone Number", "WhatsApp", "Mobile" all mean phone), so the old
KGL CUSTOMERS LIST.xlsx and the Google Sheets 'Contacts' tab both import without editing. Rows are
merged by phone number (then email), so running an import twice never creates duplicates.
"""

import csv
import io
from dataclasses import dataclass, field

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lists import merge, pack, slug
from app.models import CUSTOMER_TYPES, Contact, ContactEvent, utcnow
from app.phone import normalize_phone

HEADER_ALIASES = {
    "name": ["name", "full name", "customer name", "name of customer", "client name", "name of client", "customer", "client", "contact name"],
    "phone": ["phone", "phone number", "whatsapp", "whatsapp number", "mobile", "mobile number", "tel", "telephone", "number", "phone no"],
    "email": ["email", "email address", "e-mail"],
    "company": ["company", "business", "business name", "company name", "organisation", "organization"],
    "city": ["city", "location", "address", "area", "state"],
    "tag": ["tag", "tags", "category", "segment", "group", "type"],
    "stage": ["stage"],
    "source": ["source", "lead source"],
    "notes": ["notes", "note", "remark", "remarks", "comment", "comments"],
    "route": ["route", "routes", "lane", "service"],
    "assigned_to": ["assigned to", "account manager", "staff", "rep"],
    "opt_out": ["whatsapp opt-out", "opt out", "opt-out", "unsubscribed"],
}

# Tags and stages from the February n8n / Google Sheets system → new statuses
OLD_TAG_STATUS = {
    "major client": "vip",
    "active client": "booked",
    "existing client": "booked",
    "past client": "dormant",
    "potential client": "new",
    "high potential": "new",
    "warm": "new",
    "cold": "new",
}
OLD_STAGE_STATUS = {"lead": "new", "prospect": "quoted", "active": "booked", "past": "dormant", "churned": "lost"}
# Free-text remarks such as "existing customer" or "past customer" (matched by keyword)
REMARK_KEYWORDS = [("major", "vip"), ("existing", "booked"), ("active", "booked"), ("past", "dormant"), ("potential", "new")]


def status_from_remark(text: str) -> str | None:
    text = text.lower()
    return next((status for word, status in REMARK_KEYWORDS if word in text), None)


@dataclass
class ImportReport:
    rows: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    problems: list[str] = field(default_factory=list)


def _read_rows(filename: str, data: bytes) -> list[dict[str, str]]:
    if filename.lower().endswith((".xlsx", ".xlsm")):
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.worksheets[0]
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        # First row with at least two non-empty cells is the header (lists often start with a title row)
        start = next((i for i, r in enumerate(rows) if sum(1 for c in r if c not in (None, "")) >= 2), None)
        if start is None:
            return []
        header = ["" if h is None else str(h) for h in rows[start]]
        return [
            {header[i]: ("" if v is None else str(v)) for i, v in enumerate(r) if i < len(header)}
            for r in rows[start + 1:]
        ]
    text = data.decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def _map_headers(headers: list[str]) -> dict[str, str]:
    """field -> original header"""
    mapping: dict[str, str] = {}
    normalized = {h: " ".join(h.strip().lower().replace("_", " ").split()) for h in headers if h}
    for fieldname, aliases in HEADER_ALIASES.items():
        for original, norm in normalized.items():
            if norm in aliases and fieldname not in mapping:
                mapping[fieldname] = original
    return mapping


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in {"true", "yes", "y", "1", "x"}


def import_contacts(
    db: Session,
    filename: str,
    data: bytes,
    *,
    opt_in: bool = False,
    source: str = "old_list",
    customer_type: str = "",
    extra_tag: str = "",
) -> ImportReport:
    report = ImportReport()
    rows = _read_rows(filename, data)
    if not rows:
        report.problems.append("The file has no rows.")
        return report
    cols = _map_headers(list(rows[0].keys()))
    if "phone" not in cols and "email" not in cols:
        report.problems.append("No phone or email column found. Name a column 'Phone' or 'Email'.")
        return report
    if customer_type and customer_type not in CUSTOMER_TYPES:
        customer_type = ""

    now = utcnow()
    seen_in_file: set[str] = set()
    for line_no, row in enumerate(rows, start=2):
        get = lambda f: str(row.get(cols[f], "") or "").strip() if f in cols else ""  # noqa: E731
        raw_phone, email = get("phone"), get("email").lower() or None
        if not any(str(v).strip() for v in row.values()):
            continue
        report.rows += 1
        phone = normalize_phone(raw_phone)
        if not phone and not email:
            report.skipped += 1
            if len(report.problems) < 50:
                report.problems.append(f"Row {line_no}: no usable phone or email ({raw_phone or 'blank'})")
            continue
        key = phone or email
        if key in seen_in_file:
            # Same person twice in one file: keep one profile, but don't lose the better status or extra notes
            report.skipped += 1
            twin = (db.scalar(select(Contact).where(Contact.phone == phone)) if phone
                    else db.scalar(select(Contact).where(Contact.email == email)))
            if twin is not None:
                dup_status = (
                    OLD_TAG_STATUS.get(get("tag").lower()) or OLD_STAGE_STATUS.get(get("stage").lower())
                    or status_from_remark(get("notes")) or "new"
                )
                if twin.status == "new" and dup_status != "new":
                    twin.status = dup_status
                if get("notes") and get("notes") not in twin.notes:
                    twin.notes = (twin.notes + "\n" + get("notes")).strip()
                if not twin.name and get("name"):
                    twin.name = get("name")
            continue
        seen_in_file.add(key)

        contact = None
        if phone:
            contact = db.scalar(select(Contact).where(Contact.phone == phone))
        if contact is None and email:
            contact = db.scalar(select(Contact).where(Contact.email == email))

        tag_value = get("tag").lower()
        stage_value = get("stage").lower()
        status = (
            OLD_TAG_STATUS.get(tag_value) or OLD_STAGE_STATUS.get(stage_value) or status_from_remark(get("notes")) or "new"
        )
        tags = [t for t in [tag_value, extra_tag] if t and t not in OLD_TAG_STATUS and t != "do not contact"]
        dnc = tag_value == "do not contact"
        opted_out = _truthy(get("opt_out"))

        if contact is None:
            contact = Contact(
                name=get("name"), phone=phone, email=email, company=get("company"), city=get("city"),
                customer_type=customer_type or ("business" if get("company") else "individual"),
                status=status, source=slug(get("source")) or source, tags=pack(tags),
                routes=pack([r for r in get("route").replace(";", ",").split(",") if r.strip()]),
                notes=get("notes"), assigned_to=get("assigned_to"),
                do_not_contact=dnc, wa_opted_out=opted_out,
                wa_opt_in=opt_in and not opted_out and not dnc, wa_opt_in_at=now if opt_in else None,
            )
            db.add(contact)
            db.flush()
            db.add(ContactEvent(contact_id=contact.id, kind="import", title=f"Imported from {filename}"))
            report.created += 1
        else:
            # Fill gaps only; never overwrite what staff already edited
            for attr in ("name", "company", "city", "assigned_to"):
                if not getattr(contact, attr) and get(attr):
                    setattr(contact, attr, get(attr))
            contact.phone = contact.phone or phone
            contact.email = contact.email or email
            if get("notes") and get("notes") not in contact.notes:
                contact.notes = (contact.notes + "\n" + get("notes")).strip()
            contact.tags = merge(contact.tags, tags)
            contact.do_not_contact = contact.do_not_contact or dnc
            contact.wa_opted_out = contact.wa_opted_out or opted_out
            if opt_in and not contact.wa_opt_in and not contact.wa_opted_out:
                contact.wa_opt_in, contact.wa_opt_in_at = True, now
            report.updated += 1
    db.commit()
    return report
