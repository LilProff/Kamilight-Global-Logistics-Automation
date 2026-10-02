"""Import KGL's customer lists (Excel or CSV) into the database.

Column names are matched loosely ("Phone Number", "WhatsApp", "Mobile" all mean phone), so the old
KGL CUSTOMERS LIST.xlsx and the Google Sheets 'Contacts' tab both import without editing. Rows are
merged by phone number (then email), so running an import twice never creates duplicates.

Nothing in the sheet is thrown away: a customer whose number is missing or wrong still gets a profile
(tagged fix-phone, with the number exactly as written kept in the notes) so staff can correct it later.
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

FIX_PHONE_TAG = "fix-phone"

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
    "sn": ["s/n", "sn", "s.n", "s n", "no", "no.", "serial", "serial no"],
}

# Column sizes in the database; longer text is cut so one messy cell can never fail a whole import on Postgres
CAPS = {"name": 200, "company": 200, "city": 120, "assigned_to": 120, "email": 200, "source": 30}

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
    skipped: int = 0  # duplicates folded into an earlier row, and blank rows
    needs_fix: int = 0  # created without a usable number
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


def _cap(field_name: str, value: str) -> str:
    return " ".join(value.split())[: CAPS[field_name]] if field_name in ("name", "company", "city") else value[: CAPS[field_name]]


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
        if not any(str(v).strip() for v in row.values()):
            continue
        report.rows += 1
        raw_phone, email = get("phone"), (get("email").lower()[: CAPS["email"]] or None)
        name = _cap("name", get("name"))
        phone = normalize_phone(raw_phone)
        fix_phone = False
        if not phone and not email:
            if not name:
                report.skipped += 1
                if len(report.problems) < 50:
                    report.problems.append(f"Row {line_no}: no name, phone or email, so there was nothing to keep")
                continue
            fix_phone = True

        tag_value = get("tag").lower()
        stage_value = get("stage").lower()
        remark = get("notes")
        status = OLD_TAG_STATUS.get(tag_value) or OLD_STAGE_STATUS.get(stage_value) or status_from_remark(remark) or "new"

        # ---- find who this row is ----
        contact = None
        if fix_phone:
            key = f"fix|{name.lower()}|{raw_phone}"
            contact = db.scalar(
                select(Contact).where(Contact.phone.is_(None), Contact.name == name, Contact.tags.like(f"%,{FIX_PHONE_TAG},%"))
            )
        else:
            key = phone or email
            if phone:
                contact = db.scalar(select(Contact).where(Contact.phone == phone))
            if contact is None and email:
                contact = db.scalar(select(Contact).where(Contact.email == email))

        if key in seen_in_file and contact is not None:
            # Same person twice in one file: keep one profile, but don't lose the better status or extra notes
            report.skipped += 1
            if contact.status == "new" and status != "new":
                contact.status = status
            if remark and remark not in contact.notes:
                contact.notes = (contact.notes + "\n" + remark).strip()
            if not contact.name and name:
                contact.name = name
            continue
        seen_in_file.add(key)

        tags = [t for t in [tag_value, extra_tag] if t and t not in OLD_TAG_STATUS and t != "do not contact"]
        if fix_phone:
            tags.append(FIX_PHONE_TAG)
        dnc = tag_value == "do not contact"
        opted_out = _truthy(get("opt_out"))
        notes = remark
        if fix_phone:
            what = f"Number in the sheet: {raw_phone}" if raw_phone else "No phone number in the sheet"
            sn = f" (list S/N {get('sn')})" if get("sn") else ""
            notes = (f"{remark}\n" if remark else "") + f"{what}{sn}. Needs a valid WhatsApp number."

        if contact is None:
            contact = Contact(
                name=name, phone=phone, email=email, company=_cap("company", get("company")), city=_cap("city", get("city")),
                customer_type=customer_type or ("business" if get("company") else "individual"),
                status=status, source=slug(get("source"))[: CAPS["source"]] or source, tags=pack(tags)[:500],
                routes=pack([r for r in get("route").replace(";", ",").split(",") if r.strip()])[:500],
                notes=notes, assigned_to=_cap("assigned_to", get("assigned_to")),
                do_not_contact=dnc, wa_opted_out=opted_out,
                wa_opt_in=opt_in and not opted_out and not dnc and not fix_phone, wa_opt_in_at=now if opt_in and not fix_phone else None,
            )
            db.add(contact)
            db.flush()
            db.add(ContactEvent(contact_id=contact.id, kind="import", title=f"Imported from {filename}"))
            report.created += 1
            if fix_phone:
                report.needs_fix += 1
                if len(report.problems) < 50:
                    report.problems.append(f"Row {line_no}: {name}: kept without a WhatsApp number ({raw_phone or 'blank'}); tagged {FIX_PHONE_TAG}")
        else:
            # Fill gaps only; never overwrite what staff already edited
            for attr, value in (("name", name), ("company", _cap("company", get("company"))), ("city", _cap("city", get("city"))),
                                ("assigned_to", _cap("assigned_to", get("assigned_to")))):
                if not getattr(contact, attr) and value:
                    setattr(contact, attr, value)
            contact.phone = contact.phone or phone
            contact.email = contact.email or email
            if notes and notes not in contact.notes:
                contact.notes = (contact.notes + "\n" + notes).strip()
            contact.tags = merge(contact.tags, tags)
            contact.do_not_contact = contact.do_not_contact or dnc
            contact.wa_opted_out = contact.wa_opted_out or opted_out
            if opt_in and not contact.wa_opt_in and not contact.wa_opted_out and contact.phone:
                contact.wa_opt_in, contact.wa_opt_in_at = True, now
            report.updated += 1
    db.commit()
    return report
