"""The shared WhatsApp inbox: every conversation, who needs a person, and replying from the dashboard."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.ai import WINDOW, get_conversation, record_outbound
from app.auth import current_user
from app.db import get_db
from app.messaging import send_text
from app.models import Contact, ContactEvent, Conversation, Message, utcnow

router = APIRouter(prefix="/api/inbox", tags=["inbox"], dependencies=[Depends(current_user)])


class ReplyIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class PauseIn(BaseModel):
    paused: bool


def _window_open(contact: Contact) -> bool:
    return bool(contact.last_inbound_at and utcnow() - contact.last_inbound_at <= WINDOW)


def _row(conv: Conversation, contact: Contact) -> dict:
    return {
        "contact_id": contact.id, "name": contact.name, "phone": contact.phone, "status": contact.status,
        "last_message_at": conv.last_message_at, "preview": conv.last_inbound_text,
        "needs_human": conv.needs_human, "handoff_reason": conv.handoff_reason, "ai_paused": conv.ai_paused,
        "unread": conv.unread, "window_open": _window_open(contact),
    }


@router.get("")
def list_chats(view: str = "all", q: str = "", db: Session = Depends(get_db)):
    stmt = select(Conversation, Contact).join(Contact, Contact.id == Conversation.contact_id)
    if view == "needs_human":
        stmt = stmt.where(Conversation.needs_human.is_(True))
    elif view == "unread":
        stmt = stmt.where(Conversation.unread.is_(True))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(or_(func.lower(Contact.name).like(like), Contact.phone.like(f"%{q.strip()}%")))
    rows = db.execute(stmt.order_by(Conversation.needs_human.desc(), Conversation.last_message_at.desc()).limit(200)).all()
    return [_row(conv, contact) for conv, contact in rows]


@router.get("/summary")
def summary(db: Session = Depends(get_db)):
    count = lambda *w: db.scalar(select(func.count()).select_from(Conversation).where(*w))  # noqa: E731
    return {"needs_human": count(Conversation.needs_human.is_(True)), "unread": count(Conversation.unread.is_(True))}


@router.get("/{contact_id}")
def open_chat(contact_id: int, db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Customer not found")
    conv = get_conversation(db, contact_id)
    if conv.unread:
        conv.unread = False
    db.commit()
    msgs = db.scalars(select(Message).where(Message.contact_id == contact_id).order_by(Message.id.desc()).limit(200)).all()[::-1]
    return {
        **_row(conv, contact),
        "do_not_contact": contact.do_not_contact or contact.wa_opted_out,
        "messages": [
            {"id": m.id, "direction": m.direction, "sender": m.sender, "body": m.body, "at": m.created_at,
             "staff_email": m.staff_email, "error": m.error}
            for m in msgs
        ],
    }


@router.post("/{contact_id}/reply", status_code=201)
def reply(contact_id: int, body: ReplyIn, who: str = Depends(current_user), db: Session = Depends(get_db)):
    contact = db.get(Contact, contact_id)
    if contact is None:
        raise HTTPException(404, "Customer not found")
    if not contact.phone:
        raise HTTPException(409, "This customer has no WhatsApp number yet.")
    if contact.do_not_contact or contact.wa_opted_out:
        raise HTTPException(409, "This customer asked not to be messaged.")
    if not _window_open(contact):
        raise HTTPException(409, "WhatsApp only allows free replies within 24 hours of the customer's last message. Send an approved template from Campaigns instead.")
    text = body.text.strip()
    sent = send_text(contact, text)
    if not sent.ok:
        raise HTTPException(502, f"WhatsApp didn't accept the message: {sent.error}")
    record_outbound(db, contact, text, "staff", sent.message_id, staff_email=who)
    conv = get_conversation(db, contact_id)
    conv.needs_human, conv.unread, conv.ai_paused = False, False, True  # a person is in charge now; the AI stays quiet
    db.commit()
    return {"ok": True}


@router.post("/{contact_id}/ai")
def set_ai_paused(contact_id: int, body: PauseIn, db: Session = Depends(get_db)):
    if db.get(Contact, contact_id) is None:
        raise HTTPException(404, "Customer not found")
    conv = get_conversation(db, contact_id)
    conv.ai_paused = body.paused
    if not body.paused:
        conv.needs_human = False  # handing back to the AI
    db.commit()
    return {"ai_paused": conv.ai_paused}


@router.post("/{contact_id}/resolve")
def resolve(contact_id: int, db: Session = Depends(get_db)):
    if db.get(Contact, contact_id) is None:
        raise HTTPException(404, "Customer not found")
    conv = get_conversation(db, contact_id)
    conv.needs_human, conv.unread = False, False
    db.add(ContactEvent(contact_id=contact_id, kind="note", title="Conversation marked as handled"))
    db.commit()
    return {"ok": True}
