import io
from datetime import timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.filters import contacts_query
from app.importer import import_contacts
from app.messaging import WhatsAppSender
from app.models import Campaign, Contact, utcnow
from app.phone import normalize_phone
from app.status import record_shipment, sweep_dormant


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("08012345678", "+2348012345678"),
        ("0801 234 5678", "+2348012345678"),
        ("+234 801 234 5678", "+2348012345678"),
        ("2348012345678", "+2348012345678"),
        ("8012345678", "+2348012345678"),  # Excel dropped the leading zero
        ("8012345678.0", "+2348012345678"),  # Excel stored it as a float
        ("23408012345678", "+2348012345678"),
        ("+447911123456", "+447911123456"),
        ("12345", None),
        ("", None),
        (None, None),
        ("080123", None),
        ("0803333333", None),  # one digit short
        ("447911123456", "+447911123456"),  # international without +
    ],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def _xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_maps_columns_tags_and_dedupes(db):
    data = _xlsx([
        ["KGL CUSTOMERS LIST"],  # title row above the header
        ["Customer Name", "Phone Number", "Email", "Tag", "Location"],
        ["Ada Obi", "08031111111", "", "active client", "Ikeja"],
        ["Ada O. (dup)", "+234 803 111 1111", "", "", ""],
        ["Bayo", 8032222222, "bayo@x.com", "past client", "Lekki"],
        ["Chika", "0803333333", "", "", ""],  # too short, no email
        ["Dele", "08034444444", "", "do not contact", ""],
        ["Efe", "", "efe@x.com", "major client", ""],
        [None, None, None, None, None],
    ])
    report = import_contacts(db, "list.xlsx", data, opt_in=True)
    assert (report.rows, report.created, report.skipped) == (6, 4, 2)
    ada = db.scalar(select(Contact).where(Contact.phone == "+2348031111111"))
    assert (ada.name, ada.status, ada.city, ada.wa_opt_in) == ("Ada Obi", "booked", "Ikeja", True)
    assert db.scalar(select(Contact).where(Contact.phone == "+2348032222222")).status == "dormant"
    dele = db.scalar(select(Contact).where(Contact.phone == "+2348034444444"))
    assert dele.do_not_contact and not dele.wa_opt_in
    assert db.scalar(select(Contact).where(Contact.email == "efe@x.com")).status == "vip"

    again = import_contacts(db, "list.xlsx", data)
    assert again.created == 0 and again.updated == 4
    assert db.scalar(select(Contact).where(Contact.phone == "+2348031111111")).name == "Ada Obi"


def test_import_csv_without_phone_or_email_column(db):
    report = import_contacts(db, "x.csv", b"Name,City\nA,Lagos\n")
    assert report.created == 0 and "No phone or email column" in report.problems[0]


def test_status_follows_shipments_and_goes_dormant(db):
    c = Contact(name="Tola", phone="+2348050000000")
    db.add(c)
    db.flush()
    record_shipment(db, c, 150_000, "China Air")
    assert c.status == "booked" and c.last_route == "china-air" and c.route_list == ["china-air"]
    record_shipment(db, c, 200_000, "china-sea")
    assert c.status == "repeat" and c.shipments_count == 2 and c.total_spend_ngn == 350_000
    for _ in range(3):
        record_shipment(db, c, 10_000)
    assert c.status == "vip"
    c.last_shipment_at = utcnow() - timedelta(days=61)
    db.commit()
    assert sweep_dormant(db) == 1
    db.refresh(c)
    assert c.status == "dormant"


def test_filters(db):
    old = utcnow() - timedelta(days=90)
    db.add_all([
        Contact(name="A", phone="+2348060000001", routes=",china-air,", status="dormant", last_shipment_at=old, shipments_count=2, total_spend_ngn=300_000, city="Lagos"),
        Contact(name="B", phone="+2348060000002", routes=",lagos-uk,", status="repeat", last_shipment_at=utcnow(), shipments_count=3, customer_type="diaspora"),
        Contact(name="C", phone="+2348060000003", status="new", tags=",festive-2025,"),
    ])
    db.commit()
    names = lambda spec: sorted(c.name for c in db.scalars(contacts_query(spec)))  # noqa: E731
    assert names({"routes_any": ["China Air"], "not_shipped_for_days": 60}) == ["A"]
    assert names({"customer_types": ["diaspora"]}) == ["B"]
    assert names({"never_shipped": True}) == ["C"]
    assert names({"tags_any": ["festive-2025"]}) == ["C"]
    assert names({"min_spend": 250_000, "cities": ["lagos"]}) == ["A"]
    assert names({"search": "8060000002"}) == ["B"]
    assert names({"statuses": ["dormant", "repeat"]}) == ["A", "B"]


def test_whatsapp_payloads():
    contact = Contact(name="Ngozi Eze", phone="+2348012345678", city="Ikeja")
    template = Campaign(
        name="t", wa_template_name="cutoff_reminder", wa_template_lang="en", wa_template_params=["first_name", "city"],
        media_url="https://x/flyer.jpg", media_type="image",
    )
    p = WhatsAppSender.payload(contact, template, "")
    assert p["to"] == "2348012345678" and p["type"] == "template"
    assert p["template"]["components"][0] == {"type": "header", "parameters": [{"type": "image", "image": {"link": "https://x/flyer.jpg"}}]}
    assert [x["text"] for x in p["template"]["components"][1]["parameters"]] == ["Ngozi", "Ikeja"]

    text = WhatsAppSender.payload(contact, Campaign(name="t", media_url="", media_type="", wa_template_params=[]), "Hi Ngozi")
    assert text["type"] == "text" and text["text"]["body"] == "Hi Ngozi"

    doc = WhatsAppSender.payload(contact, Campaign(name="t", media_url="https://x/rates.pdf", media_type="document", wa_template_params=[]), "Rates")
    assert doc["type"] == "document" and doc["document"] == {"link": "https://x/rates.pdf", "caption": "Rates"}
