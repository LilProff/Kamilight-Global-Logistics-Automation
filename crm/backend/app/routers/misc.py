"""Login, dashboard numbers, and the public WhatsApp webhook."""

import hashlib
import hmac
import json
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import check_login, current_user, issue_token
from app.config import get_settings
from app.db import get_db
from app.inbound import handle_webhook
from app.messaging import channel_live
from app.models import Campaign, CampaignRecipient, Contact, utcnow
from app.schemas import LoginIn

router = APIRouter(prefix="/api")


@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn):
    if not check_login(body.email, body.password):
        raise HTTPException(401, "Email or password is wrong.")
    return {"token": issue_token(body.email), "email": body.email}


@router.get("/auth/me", tags=["auth"])
def me(user: str = Depends(current_user)):
    return {"email": user}


@router.get("/stats", tags=["dashboard"], dependencies=[Depends(current_user)])
def stats(db: Session = Depends(get_db)):
    since = utcnow() - timedelta(days=30)
    by_status = dict(db.execute(select(Contact.status, func.count()).group_by(Contact.status)).all())
    count = lambda *where: db.scalar(select(func.count()).select_from(Contact).where(*where))  # noqa: E731
    sent_30d = db.scalar(
        select(func.count()).select_from(CampaignRecipient)
        .where(CampaignRecipient.sent_at >= since, CampaignRecipient.status.in_(["sent", "delivered", "read"]))
    )
    replied_30d = db.scalar(
        select(func.count()).select_from(CampaignRecipient).where(CampaignRecipient.sent_at >= since, CampaignRecipient.replied.is_(True))
    )
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "marketing_consent": count(Contact.wa_opt_in.is_(True), Contact.wa_opted_out.is_(False), Contact.do_not_contact.is_(False)),
        "opted_out": count(Contact.wa_opted_out.is_(True)),
        "new_last_30d": count(Contact.created_at >= since),
        "campaigns_last_30d": db.scalar(select(func.count()).select_from(Campaign).where(Campaign.started_at >= since)),
        "messages_sent_30d": sent_30d,
        "replies_30d": replied_30d,
        "channels": {"whatsapp": channel_live("whatsapp"), "email": channel_live("email")},
    }


@router.get("/webhooks/whatsapp", tags=["webhooks"], response_class=PlainTextResponse)
def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    """Meta calls this once when the webhook URL is registered."""
    if mode == "subscribe" and hmac.compare_digest(token, get_settings().wa_verify_token):
        return challenge
    raise HTTPException(403, "Verification failed")


@router.post("/webhooks/whatsapp", tags=["webhooks"])
async def receive(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    secret = get_settings().wa_app_secret
    if secret:
        expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, request.headers.get("x-hub-signature-256", "")):
            raise HTTPException(403, "Bad signature")
    try:
        payload = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON") from None
    return handle_webhook(db, payload)
