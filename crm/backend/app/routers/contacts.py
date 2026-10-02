import csv
import io
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import current_user
from app.db import get_db
from app.filters import apply_filters, contacts_query
from app.importer import import_contacts
from app.lists import pack, unpack
from app.models import CUSTOMER_TYPES, SOURCES, STATUSES, Contact, ContactEvent, utcnow
from app.phone import normalize_phone
from app.schemas import (
    ContactCreate, ContactDetail, ContactOut, ContactPage, ContactUpdate, EventOut, ImportResult, NoteIn, ShipmentIn,
)
from app.status import mark_quoted, record_shipment, set_status

router = APIRouter(prefix="/api/contacts", tags=["contacts"], dependencies=[Depends(current_user)])

DEFAULT_ROUTES = ["china-air", "china-sea", "uk-import", "us-import", "lagos-uk", "lagos-us", "lagos-canada", "clearing", "haulage"]
SORTS = {
    "recent": Contact.updated_at.desc(),
    "name": Contact.name.asc(),
    "spend": Contact.total_spend_ngn.desc(),
    "last_shipment": Contact.last_shipment_at.desc(),
    "created": Contact.created_at.desc(),
}


def _safe_cell(column: str, value):
    """Stop spreadsheet formula injection: a customer named =HYPERLINK(...) must not run when staff open the CSV in Excel."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        if column == "phone" and value[1:].isdigit():
            return value  # a real number like +2348012345678
        return "'" + value
    return value


class SearchIn(BaseModel):
    filters: dict = {}
    page: int = 1
    page_size: int = 50
    sort: Literal["recent", "name", "spend", "last_shipment", "created"] = "recent"


def _get(db: Session, contact_id: int) -> Contact:
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Customer not found")
    return contact


def _clean_phone(db: Session, raw: str | None, exclude_id: int | None = None) -> str | None:
    if raw in (None, ""):
        return None
    phone = normalize_phone(raw)
    if phone is None:
        raise HTTPException(422, f"'{raw}' isn't a valid phone number. Use a format like 08012345678 or +2348012345678.")
    clash = db.scalar(select(Contact).where(Contact.phone == phone, Contact.id != (exclude_id or 0)))
    if clash:
        raise HTTPException(409, f"{phone} already belongs to {clash.name or 'another customer'} (#{clash.id}).")
    return phone


@router.post("/search", response_model=ContactPage)
def search(body: SearchIn, db: Session = Depends(get_db)):
    page_size = min(max(body.page_size, 1), 200)
    page = max(body.page, 1)
    q = contacts_query(body.filters)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    items = db.scalars(q.order_by(SORTS[body.sort], Contact.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return ContactPage(items=items, total=total, page=page, page_size=page_size)


@router.post("/export")
def export(body: SearchIn, db: Session = Depends(get_db)):
    cols = ["id", "name", "phone", "email", "company", "city", "customer_type", "status", "source", "routes", "tags",
            "shipments_count", "total_spend_ngn", "last_shipment_at", "wa_opt_in", "wa_opted_out", "do_not_contact",
            "assigned_to", "notes"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(cols)
    for c in db.scalars(contacts_query(body.filters).order_by(Contact.id)):
        w.writerow([_safe_cell(k, ", ".join(unpack(getattr(c, k))) if k in ("routes", "tags") else getattr(c, k)) for k in cols])
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="kgl-customers.csv"'},
    )


@router.get("/options")
def options(db: Session = Depends(get_db)):
    """Values for the filter builder's dropdowns."""
    routes, tags = set(DEFAULT_ROUTES), set()
    for r, t in db.execute(select(Contact.routes, Contact.tags)):
        routes.update(unpack(r))
        tags.update(unpack(t))
    cities = [c for c in db.scalars(select(Contact.city).where(Contact.city != "").distinct().order_by(Contact.city))]
    staff = [s for s in db.scalars(select(Contact.assigned_to).where(Contact.assigned_to != "").distinct())]
    return {
        "statuses": STATUSES, "customer_types": CUSTOMER_TYPES, "sources": SOURCES,
        "routes": sorted(routes), "tags": sorted(tags), "cities": cities, "staff": sorted(staff),
    }


@router.post("", response_model=ContactOut, status_code=201)
def create(body: ContactCreate, db: Session = Depends(get_db)):
    data = body.model_dump()
    data["phone"] = _clean_phone(db, body.phone)
    data["email"] = (body.email or "").strip().lower() or None
    if not data["phone"] and not data["email"]:
        raise HTTPException(422, "Add a phone number or an email.")
    data["routes"], data["tags"] = pack(body.routes), pack(body.tags)
    contact = Contact(**data)
    if body.wa_opt_in:
        contact.wa_opt_in_at = utcnow()
    db.add(contact)
    db.flush()
    db.add(ContactEvent(contact_id=contact.id, kind="status", title="Customer added"))
    db.commit()
    return contact


@router.get("/{contact_id}", response_model=ContactDetail)
def detail(contact_id: int, db: Session = Depends(get_db)):
    contact = _get(db, contact_id)
    out = ContactDetail.model_validate(contact)
    out.events = [EventOut.model_validate(e) for e in contact.events[:200]]
    return out


@router.patch("/{contact_id}", response_model=ContactOut)
def update(contact_id: int, body: ContactUpdate, db: Session = Depends(get_db)):
    contact = _get(db, contact_id)
    data = body.model_dump(exclude_unset=True)
    if "phone" in data:
        contact.phone = _clean_phone(db, data.pop("phone"), exclude_id=contact.id)
    if "email" in data:
        contact.email = (data.pop("email") or "").strip().lower() or None
    if "routes" in data:
        contact.routes = pack(data.pop("routes") or [])
    if "tags" in data:
        contact.tags = pack(data.pop("tags") or [])
    if "status" in data:
        new = data.pop("status")
        reason = (data.get("lost_reason") or "") if new == "lost" else ""
        set_status(db, contact, new, f"Changed by staff{': ' + reason if reason else ''}")
    if "wa_opt_in" in data:
        opt_in = data.pop("wa_opt_in")
        if opt_in and not contact.wa_opt_in:
            contact.wa_opt_in, contact.wa_opt_in_at, contact.wa_opted_out = True, utcnow(), False
            db.add(ContactEvent(contact_id=contact.id, kind="opt_in", title="Marketing consent recorded by staff"))
        elif not opt_in and contact.wa_opt_in:
            contact.wa_opt_in = False
            db.add(ContactEvent(contact_id=contact.id, kind="opt_out", title="Marketing consent removed by staff"))
    for key, value in data.items():
        setattr(contact, key, value)
    db.commit()
    return contact


@router.delete("/{contact_id}", status_code=204)
def delete(contact_id: int, db: Session = Depends(get_db)):
    db.delete(_get(db, contact_id))
    db.commit()


@router.post("/{contact_id}/shipments", response_model=ContactOut)
def add_shipment(contact_id: int, body: ShipmentIn, db: Session = Depends(get_db)):
    contact = _get(db, contact_id)
    record_shipment(db, contact, body.amount_ngn, body.route, body.note, body.shipped_at)
    db.commit()
    return contact


@router.post("/{contact_id}/quote", response_model=ContactOut)
def add_quote(contact_id: int, body: NoteIn, db: Session = Depends(get_db)):
    contact = _get(db, contact_id)
    mark_quoted(db, contact, body.text)
    db.commit()
    return contact


@router.post("/{contact_id}/notes", response_model=EventOut, status_code=201)
def add_note(contact_id: int, body: NoteIn, db: Session = Depends(get_db)):
    contact = _get(db, contact_id)
    event = ContactEvent(contact_id=contact.id, kind="note", title="Note", detail=body.text)
    db.add(event)
    db.commit()
    return event


@router.post("/import", response_model=ImportResult)
async def upload(
    file: UploadFile = File(...),
    opt_in: bool = Form(False),
    source: str = Form("old_list"),
    customer_type: str = Form(""),
    extra_tag: str = Form(""),
    db: Session = Depends(get_db),
):
    name = file.filename or "upload.csv"
    if not name.lower().endswith((".csv", ".xlsx", ".xlsm")):
        raise HTTPException(422, "Upload an Excel (.xlsx) or CSV file.")
    data = await file.read()
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(413, "File is larger than 20 MB.")
    report = import_contacts(db, name, data, opt_in=opt_in, source=source, customer_type=customer_type, extra_tag=extra_tag)
    return ImportResult(**report.__dict__)


def filtered_count(db: Session, spec: dict) -> int:
    return db.scalar(select(func.count()).select_from(apply_filters(select(Contact.id), spec).subquery()))
