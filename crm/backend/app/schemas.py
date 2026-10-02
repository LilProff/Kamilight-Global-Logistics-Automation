import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.lists import unpack

Status = Literal["new", "quoted", "booked", "repeat", "vip", "dormant", "lost"]
CustomerType = Literal["individual", "online_seller", "business", "diaspora", "partner"]
Channel = Literal["whatsapp", "email"]
Category = Literal["marketing", "utility"]


class ContactBase(BaseModel):
    name: str = ""
    phone: str | None = None
    email: str | None = None
    company: str = ""
    city: str = ""
    customer_type: CustomerType = "individual"
    source: str = "manual"
    routes: list[str] = []
    tags: list[str] = []
    goods: str = ""
    preferred_mode: str = ""
    assigned_to: str = ""
    notes: str = ""
    birthday: str = ""
    wa_opt_in: bool = False
    do_not_contact: bool = False
    next_follow_up: datetime | None = None


LIMITS = {"name": 200, "phone": 40, "email": 200, "company": 200, "city": 120, "goods": 300, "assigned_to": 120,
          "notes": 5000, "lost_reason": 300, "birthday": 5, "source": 30, "preferred_mode": 10}


def _check_lengths(values: dict) -> dict:
    for field, limit in LIMITS.items():
        v = values.get(field)
        if isinstance(v, str) and len(v) > limit:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long (the limit is {limit} characters).")
    return values


class ContactCreate(ContactBase):
    status: Status = "new"

    @model_validator(mode="before")
    @classmethod
    def _limits(cls, values):
        return _check_lengths(values) if isinstance(values, dict) else values


class ContactUpdate(BaseModel):
    """Every field optional: only what's sent changes."""

    @model_validator(mode="before")
    @classmethod
    def _limits(cls, values):
        return _check_lengths(values) if isinstance(values, dict) else values

    name: str | None = None
    phone: str | None = None
    email: str | None = None
    company: str | None = None
    city: str | None = None
    customer_type: CustomerType | None = None
    status: Status | None = None
    lost_reason: str | None = None
    source: str | None = None
    routes: list[str] | None = None
    tags: list[str] | None = None
    goods: str | None = None
    preferred_mode: str | None = None
    assigned_to: str | None = None
    notes: str | None = None
    birthday: str | None = None
    wa_opt_in: bool | None = None
    do_not_contact: bool | None = None
    next_follow_up: datetime | None = None


class ContactOut(ContactBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: Status
    lost_reason: str
    shipments_count: int
    total_spend_ngn: float
    first_shipment_at: datetime | None
    last_shipment_at: datetime | None
    last_route: str
    wa_opt_in_at: datetime | None
    wa_opted_out: bool
    last_inbound_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @field_validator("routes", "tags", mode="before")
    @classmethod
    def _unpack(cls, v):
        return unpack(v) if isinstance(v, str) else v


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    title: str
    detail: str
    amount_ngn: float | None
    created_at: datetime


class ContactDetail(ContactOut):
    events: list[EventOut] = []


class ContactPage(BaseModel):
    items: list[ContactOut]
    total: int
    page: int
    page_size: int


class ShipmentIn(BaseModel):
    amount_ngn: float = Field(ge=0)
    route: str = ""
    note: str = ""
    shipped_at: datetime | None = None


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class ImportResult(BaseModel):
    rows: int
    created: int
    updated: int
    skipped: int
    needs_fix: int = 0
    problems: list[str]


class SegmentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    filters: dict = {}


class SegmentOut(SegmentIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    count: int = 0


class PreviewIn(BaseModel):
    filters: dict = {}
    segment_id: int | None = None
    channel: Channel = "whatsapp"
    category: Category = "marketing"


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    channel: Channel = "whatsapp"
    category: Category = "marketing"
    filters: dict = {}
    segment_id: int | None = None
    subject: str = Field(default="", max_length=200)
    body: str = Field(default="", max_length=4000)
    media_url: str = Field(default="", max_length=500)
    media_type: Literal["", "image", "video", "document"] = ""
    wa_template_name: str = Field(default="", max_length=120, pattern=r"^[a-z0-9_]*$")
    wa_template_lang: str = Field(default="en", max_length=10)
    wa_template_params: list[str] = []

    @field_validator("media_url")
    @classmethod
    def _web_address_only(cls, v: str) -> str:
        v = v.strip()
        if v and not re.match(r"^https?://[^\s]+$", v, re.I):
            raise ValueError("The attachment link must be a web address starting with http:// or https://")
        return v

    @field_validator("wa_template_params")
    @classmethod
    def _known_placeholders(cls, v: list[str]) -> list[str]:
        allowed = {"first_name", "name", "city", "company", "last_route"}
        bad = [p for p in v if p not in allowed]
        if bad:
            raise ValueError(f"Unknown template variable(s): {', '.join(bad)}. Use: {', '.join(sorted(allowed))}.")
        return v


class CampaignOut(CampaignIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: str
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    test_mode: bool
    created_at: datetime


class ScheduleIn(BaseModel):
    send_at: datetime | None = None  # None = send now


