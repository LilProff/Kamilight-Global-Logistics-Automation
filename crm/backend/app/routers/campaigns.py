from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import campaigns as engine
from app.auth import current_user
from app.db import get_db
from app.messaging import channel_live
from app.models import Campaign, CampaignRecipient, Contact, Segment, utcnow
from app.schemas import CampaignIn, CampaignOut, PreviewIn, ScheduleIn

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"], dependencies=[Depends(current_user)])


class CampaignDetail(CampaignOut):
    report: dict
    audience: dict | None = None


def _get(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(404, "Campaign not found")
    return campaign


def _validate(db: Session, body: CampaignIn) -> None:
    if body.segment_id and db.get(Segment, body.segment_id) is None:
        raise HTTPException(422, "That segment no longer exists.")
    if body.channel == "email" and not body.subject.strip():
        raise HTTPException(422, "Email campaigns need a subject line.")
    if not body.body.strip() and not body.wa_template_name and not body.media_url:
        raise HTTPException(422, "Write a message, attach media, or pick a WhatsApp template.")
    if body.media_url and not body.media_type:
        raise HTTPException(422, "Say whether the attachment is an image, video or document.")


@router.post("/preview")
def preview(body: PreviewIn, db: Session = Depends(get_db)):
    probe = Campaign(name="preview", filters=body.filters, segment_id=body.segment_id)
    return engine.preview(db, engine.campaign_filters(db, probe), body.channel, body.category)


@router.get("", response_model=list[CampaignDetail])
def list_campaigns(db: Session = Depends(get_db)):
    rows = db.scalars(select(Campaign).order_by(Campaign.created_at.desc()).limit(200)).all()
    return [CampaignDetail(**CampaignOut.model_validate(c).model_dump(), report=engine.report(db, c)) for c in rows]


@router.post("", response_model=CampaignOut, status_code=201)
def create(body: CampaignIn, db: Session = Depends(get_db)):
    _validate(db, body)
    campaign = Campaign(**body.model_dump())
    db.add(campaign)
    db.commit()
    return campaign


@router.get("/{campaign_id}", response_model=CampaignDetail)
def detail(campaign_id: int, db: Session = Depends(get_db)):
    c = _get(db, campaign_id)
    audience = None
    if c.status in ("draft", "scheduled"):
        audience = engine.preview(db, engine.campaign_filters(db, c), c.channel, c.category)
    return CampaignDetail(**CampaignOut.model_validate(c).model_dump(), report=engine.report(db, c), audience=audience)


@router.put("/{campaign_id}", response_model=CampaignOut)
def update(campaign_id: int, body: CampaignIn, db: Session = Depends(get_db)):
    campaign = _get(db, campaign_id)
    if campaign.status not in ("draft", "scheduled"):
        raise HTTPException(409, "This campaign has already been sent and can't be edited. Duplicate it instead.")
    _validate(db, body)
    for key, value in body.model_dump().items():
        setattr(campaign, key, value)
    db.commit()
    return campaign


@router.delete("/{campaign_id}", status_code=204)
def delete(campaign_id: int, db: Session = Depends(get_db)):
    campaign = _get(db, campaign_id)
    if campaign.status == "sending":
        raise HTTPException(409, "Cancel the campaign before deleting it.")
    db.delete(campaign)
    db.commit()


@router.post("/{campaign_id}/send", response_model=CampaignDetail)
def send(campaign_id: int, body: ScheduleIn, db: Session = Depends(get_db)):
    campaign = _get(db, campaign_id)
    if campaign.status not in ("draft", "scheduled"):
        raise HTTPException(409, f"This campaign is already {campaign.status}.")
    if campaign.channel == "whatsapp" and campaign.category == "marketing" and not campaign.wa_template_name and channel_live("whatsapp"):
        # Meta only delivers free-form messages inside the 24h window after a customer's last message
        raise HTTPException(422, "WhatsApp marketing messages need an approved template. Pick one before sending.")
    if body.send_at and body.send_at > utcnow():
        campaign.status, campaign.scheduled_at = "scheduled", body.send_at
        db.commit()
    else:
        engine.start(db, campaign)
    return detail(campaign_id, db)


@router.post("/{campaign_id}/cancel", response_model=CampaignDetail)
def cancel(campaign_id: int, db: Session = Depends(get_db)):
    campaign = _get(db, campaign_id)
    if campaign.status not in ("scheduled", "sending"):
        raise HTTPException(409, f"A {campaign.status} campaign can't be cancelled.")
    for rec in db.scalars(select(CampaignRecipient).where(
        CampaignRecipient.campaign_id == campaign.id, CampaignRecipient.status == "queued"
    )):
        rec.status, rec.error = "skipped", "Campaign cancelled"
    campaign.status, campaign.finished_at = "cancelled", utcnow()
    db.commit()
    return detail(campaign_id, db)


@router.post("/{campaign_id}/duplicate", response_model=CampaignOut, status_code=201)
def duplicate(campaign_id: int, db: Session = Depends(get_db)):
    src = _get(db, campaign_id)
    copy = Campaign(**CampaignIn.model_validate(src, from_attributes=True).model_dump())
    copy.name = f"{src.name} (copy)"
    db.add(copy)
    db.commit()
    return copy


@router.get("/{campaign_id}/recipients")
def recipients(campaign_id: int, status: str | None = None, db: Session = Depends(get_db)):
    _get(db, campaign_id)
    q = (
        select(CampaignRecipient, Contact.name, Contact.phone, Contact.email)
        .join(Contact)
        .where(CampaignRecipient.campaign_id == campaign_id)
        .order_by(CampaignRecipient.id)
        .limit(1000)
    )
    if status:
        q = q.where(CampaignRecipient.status == status)
    return [
        {
            "contact_id": r.contact_id, "name": name, "phone": phone, "email": email, "status": r.status,
            "error": r.error, "replied": r.replied, "sent_at": r.sent_at, "read_at": r.read_at,
        }
        for r, name, phone, email in db.execute(q)
    ]
