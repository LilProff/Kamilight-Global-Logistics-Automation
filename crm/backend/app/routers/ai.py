"""AI assistant settings, a safe test chat, and AI-written campaign drafts."""

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai import AiError, ai_configured, draft_message, get_ai_settings, simulate
from app.auth import current_user, require_admin
from app.config import get_settings
from app.db import get_db
from app.models import Contact, Conversation, Message, utcnow

router = APIRouter(prefix="/api/ai", tags=["ai"], dependencies=[Depends(current_user)])


class SettingsIn(BaseModel):
    enabled: bool
    knowledge: str = Field(default="", max_length=20000)
    extra_instructions: str = Field(default="", max_length=4000)
    max_replies_per_day: int = Field(default=12, ge=1, le=100)


class TestIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    transcript: list[dict] = Field(default_factory=list, max_length=30)
    contact_id: int | None = None


class DraftIn(BaseModel):
    goal: str = Field(min_length=3, max_length=500)
    audience: str = Field(default="", max_length=300)
    category: str = Field(default="marketing", pattern="^(marketing|utility)$")
    channel: str = Field(default="whatsapp", pattern="^(whatsapp|email|sms)$")


def _view(db: Session) -> dict:
    cfg = get_ai_settings(db)
    since = utcnow() - timedelta(hours=24)
    sent = db.scalars(select(Message).where(Message.sender == "ai", Message.created_at >= since)).all()
    return {
        "enabled": cfg.enabled, "knowledge": cfg.knowledge, "extra_instructions": cfg.extra_instructions,
        "max_replies_per_day": cfg.max_replies_per_day, "configured": ai_configured(), "model": get_settings().ai_model,
        "ai_replies_24h": len(sent), "tokens_24h": sum(m.tokens_in + m.tokens_out for m in sent),
        "waiting_for_staff": db.scalar(select(func.count()).select_from(Conversation).where(Conversation.needs_human.is_(True))),
    }


def _need_ai() -> None:
    if not ai_configured():
        raise HTTPException(409, "The AI isn't connected yet. Add the ANTHROPIC_API_KEY setting in Render.")


@router.get("/settings")
def read_settings(db: Session = Depends(get_db)):
    return _view(db)


@router.put("/settings", dependencies=[Depends(require_admin)])
def save_settings(body: SettingsIn, db: Session = Depends(get_db)):
    if body.enabled:
        _need_ai()
        if len(body.knowledge.strip()) < 80:
            raise HTTPException(422, "Add what KGL offers (services, routes, how to book) before switching the AI on, so it only says true things.")
    cfg = get_ai_settings(db)
    cfg.enabled, cfg.knowledge = body.enabled, body.knowledge.strip()
    cfg.extra_instructions, cfg.max_replies_per_day = body.extra_instructions.strip(), body.max_replies_per_day
    db.commit()
    return _view(db)


@router.post("/test")
def test_chat(body: TestIn, db: Session = Depends(get_db)):
    """Talk to the AI as if you were a customer. Nothing is saved or sent."""
    _need_ai()
    contact = db.get(Contact, body.contact_id) if body.contact_id else None
    try:
        out = simulate(db, body.message, body.transcript, contact)
    except AiError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"reply": out.reply, "actions": out.actions, "handoff": bool(out.handoff_reason), "handoff_reason": out.handoff_reason}


@router.post("/draft")
def draft(body: DraftIn):
    _need_ai()
    try:
        return {"text": draft_message(body.goal, body.audience, body.category, body.channel)}
    except AiError as exc:
        raise HTTPException(502, str(exc)) from exc
