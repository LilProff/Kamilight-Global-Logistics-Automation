from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import automations as engine
from app.auth import current_user, require_admin
from app.db import get_db
from app.models import Automation, AutomationLog, utcnow

router = APIRouter(prefix="/api/automations", tags=["automations"], dependencies=[Depends(current_user)])


class AutomationUpdate(BaseModel):
    enabled: bool
    body: str = Field(default="", max_length=4000)
    wa_template_name: str = Field(default="", max_length=120, pattern=r"^[a-z0-9_]*$")
    wa_template_lang: str = Field(default="en", max_length=10)
    wa_template_params: list[str] = []
    days: int = Field(default=2, ge=0, le=60)
    cooldown_days: int = Field(default=60, ge=1, le=3650)
    daily_limit: int = Field(default=30, ge=1, le=500)


def _get(db: Session, key: str) -> Automation:
    auto = db.get(Automation, key) if key in engine.RULES else None
    if auto is None:
        raise HTTPException(404, "Automation not found")
    return auto


def _view(db: Session, auto: Automation) -> dict:
    rule = engine.RULES[auto.key]
    total = db.scalar(select(func.count()).select_from(AutomationLog).where(AutomationLog.automation_key == auto.key)) or 0
    last: datetime | None = db.scalar(select(func.max(AutomationLog.at)).where(AutomationLog.automation_key == auto.key))
    return {
        "key": auto.key, "title": rule.title, "summary": rule.summary, "category": rule.category,
        "uses_days": rule.uses_days, "enabled": auto.enabled, "body": auto.body,
        "wa_template_name": auto.wa_template_name, "wa_template_lang": auto.wa_template_lang,
        "wa_template_params": auto.wa_template_params or [], "days": auto.days, "cooldown_days": auto.cooldown_days,
        "daily_limit": auto.daily_limit, "sent_total": total, "last_sent_at": last,
        "in_sending_hours": engine.in_sending_hours(), "preview": engine.preview(db, auto),
    }


@router.get("")
def list_automations(db: Session = Depends(get_db)):
    return [_view(db, _get(db, key)) for key in engine.RULES]


@router.put("/{key}", dependencies=[Depends(require_admin)])
def update(key: str, body: AutomationUpdate, db: Session = Depends(get_db)):
    auto = _get(db, key)
    bad = [p for p in body.wa_template_params if p not in {"first_name", "name", "city", "company", "last_route"}]
    if bad:
        raise HTTPException(422, f"Unknown template variable(s): {', '.join(bad)}")
    auto.body, auto.wa_template_name, auto.wa_template_lang = body.body, body.wa_template_name, body.wa_template_lang
    auto.wa_template_params, auto.days, auto.cooldown_days, auto.daily_limit = body.wa_template_params, body.days, body.cooldown_days, body.daily_limit
    if body.enabled:
        reason = engine.blocked_reason(auto)
        if reason:
            raise HTTPException(422, reason)
    auto.enabled, auto.updated_at = body.enabled, utcnow()
    db.commit()
    return _view(db, auto)
