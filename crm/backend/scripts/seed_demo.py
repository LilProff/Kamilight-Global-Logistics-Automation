"""Fill a local database with sample customers for demos. All are tagged 'demo'.

    python -m scripts.seed_demo            add 80 sample customers
    python -m scripts.seed_demo --remove   delete every customer tagged 'demo'
"""

import random
import sys
from datetime import timedelta

from sqlalchemy import delete, select

from app.db import Base, SessionLocal, engine
from app.lists import pack
from app.models import Contact, ContactEvent, Segment, utcnow
from app.status import record_shipment

FIRST = ["Ada", "Bayo", "Chika", "Dele", "Efe", "Funmi", "Gbenga", "Halima", "Ifeanyi", "Jide", "Kemi", "Lola", "Musa",
         "Ngozi", "Ola", "Pelumi", "Rotimi", "Sade", "Tunde", "Uche", "Yemi", "Zainab", "Kunle", "Amaka", "Segun"]
LAST = ["Obi", "Adeyemi", "Okafor", "Balogun", "Eze", "Bello", "Nwosu", "Ogunleye", "Ibrahim", "Afolabi", "Okoro"]
CITIES = ["Ikeja", "Lekki", "Surulere", "Yaba", "Ajah", "Agege", "Abuja", "Port Harcourt", "Ibadan"]
PROFILES = [
    ("online_seller", ["china-air"], "phone accessories", "air"),
    ("online_seller", ["china-air", "china-sea"], "hair & beauty products", "both"),
    ("business", ["china-sea"], "machine parts", "sea"),
    ("diaspora", ["lagos-uk"], "foodstuff", "air"),
    ("diaspora", ["lagos-us", "lagos-canada"], "foodstuff & clothing", "air"),
    ("individual", ["clearing"], "personal effects", "sea"),
    ("individual", ["uk-import"], "electronics", "air"),
]


def seed(n: int = 80) -> None:
    rnd = random.Random(7)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for i in range(n):
            ctype, routes, goods, mode = rnd.choice(PROFILES)
            name = f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"
            phone = f"+234803{9000000 + i:07d}"
            if db.scalar(select(Contact).where(Contact.phone == phone)):
                continue
            c = Contact(
                name=name, phone=phone, city=rnd.choice(CITIES), customer_type=ctype, routes=pack(routes), goods=goods,
                preferred_mode=mode, source=rnd.choice(["old_list", "old_list", "whatsapp", "referral", "ad"]),
                tags=pack(["demo"]), wa_opt_in=rnd.random() < 0.75, created_at=utcnow() - timedelta(days=rnd.randint(1, 400)),
            )
            c.wa_opt_in_at = c.created_at if c.wa_opt_in else None
            if rnd.random() < 0.04:
                c.wa_opted_out, c.wa_opt_in = True, False
            db.add(c)
            db.flush()
            db.add(ContactEvent(contact_id=c.id, kind="import", title="Sample customer (demo data)"))
            shipments = rnd.choices([0, 1, 2, 3, 6], weights=[25, 30, 20, 15, 10])[0]
            for _ in range(shipments):
                when = utcnow() - timedelta(days=rnd.randint(3, 240))
                record_shipment(db, c, rnd.randrange(60_000, 900_000, 5_000), rnd.choice(routes), when=when)
            if shipments == 0 and rnd.random() < 0.4:
                c.status = "quoted"
        db.commit()
        for name, filters in [
            ("China importers, dormant 60+ days", {"routes_any": ["china-air", "china-sea"], "not_shipped_for_days": 60}),
            ("Diaspora senders", {"customer_types": ["diaspora"]}),
            ("VIP customers", {"statuses": ["vip"]}),
            ("Quoted but never shipped", {"statuses": ["quoted"]}),
        ]:
            if not db.scalar(select(Segment).where(Segment.name == name)):
                db.add(Segment(name=name, filters=filters, description="Demo segment"))
        db.commit()
    print(f"Added up to {n} demo customers and 4 demo segments.")


def remove() -> None:
    with SessionLocal() as db:
        ids = db.scalars(select(Contact.id).where(Contact.tags.like("%,demo,%"))).all()
        db.execute(delete(Contact).where(Contact.id.in_(ids)))
        db.execute(delete(Segment).where(Segment.description == "Demo segment"))
        db.commit()
    print(f"Removed {len(ids)} demo customers.")


if __name__ == "__main__":
    remove() if "--remove" in sys.argv else seed()
