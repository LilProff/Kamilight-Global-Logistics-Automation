import io
from datetime import timedelta

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

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
    # Chika's number is one digit short: she is kept (tagged fix-phone) rather than thrown away
    assert (report.rows, report.created, report.skipped, report.needs_fix) == (6, 5, 1, 1)
    chika = db.scalar(select(Contact).where(Contact.name == "Chika"))
    assert chika.phone is None and "fix-phone" in chika.tag_list and "0803333333" in chika.notes and not chika.wa_opt_in
    ada = db.scalar(select(Contact).where(Contact.phone == "+2348031111111"))
    assert (ada.name, ada.status, ada.city, ada.wa_opt_in) == ("Ada Obi", "booked", "Ikeja", True)
    assert db.scalar(select(Contact).where(Contact.phone == "+2348032222222")).status == "dormant"
    dele = db.scalar(select(Contact).where(Contact.phone == "+2348034444444"))
    assert dele.do_not_contact and not dele.wa_opt_in
    assert db.scalar(select(Contact).where(Contact.email == "efe@x.com")).status == "vip"

    again = import_contacts(db, "list.xlsx", data)
    assert again.created == 0 and again.updated == 5 and db.scalar(select(func.count()).select_from(Contact)) == 5
    assert db.scalar(select(Contact).where(Contact.phone == "+2348031111111")).name == "Ada Obi"


def test_import_kgl_sheet_layout_reads_name_and_status_from_remark(db):
    csv = (
        b"S/N,NAME OF CUSTOMER,PHONE NUMBER ,EMAIL,REMARK\n"
        b"1,Ada Obi,08031111111,,existing customer\n"
        b"2,Bayo,08032222222,,past customer\n"
        b"3,Chi,08033333333,,potential c\n"
        b"4,Dele,08034444444,,\n"
    )
    assert import_contacts(db, "kgl.csv", csv).created == 4
    by_name = {c.name: c for c in db.scalars(select(Contact))}
    assert {n: c.status for n, c in by_name.items()} == {"Ada Obi": "booked", "Bayo": "dormant", "Chi": "new", "Dele": "new"}
    assert by_name["Ada Obi"].notes == "existing customer"


def test_import_duplicate_rows_keep_the_better_status(db):
    csv = (
        b"NAME OF CUSTOMER,PHONE NUMBER,REMARK\n"
        b"Ada,08031111111,potential c\n"
        b"Ada O.,+234 803 111 1111,existing customer\n"
    )
    report = import_contacts(db, "kgl.csv", csv)
    assert (report.created, report.skipped) == (1, 1)
    ada = db.scalar(select(Contact))
    assert ada.status == "booked" and "existing customer" in ada.notes and "potential c" in ada.notes


def test_import_keeps_every_row_and_survives_oversized_cells(db):
    long_city = "x" * 400
    csv = (
        "S/N,NAME OF CUSTOMER,PHONE NUMBER,EMAIL,REMARK,LOCATION\n"
        f"7,Tola Adeyemi,0803 12,,existing customer,{long_city}\n"  # bad number, huge city
        "8,Nobody Phone,,,past customer,\n"  # no number at all
        ",,,,,\n"  # entirely blank
    ).encode()
    report = import_contacts(db, "x.csv", csv)
    assert (report.created, report.needs_fix) == (2, 2)
    tola = db.scalar(select(Contact).where(Contact.name == "Tola Adeyemi"))
    assert tola.status == "booked" and len(tola.city) == 120  # cut to the column size, not an error
    assert "0803 12" in tola.notes and "list S/N 7" in tola.notes and tola.phone is None
    nobody = db.scalar(select(Contact).where(Contact.name == "Nobody Phone"))
    assert nobody.status == "dormant" and "No phone number in the sheet" in nobody.notes
    # importing the same sheet again does not duplicate them
    assert import_contacts(db, "x.csv", csv).created == 0


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
