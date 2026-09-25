"""Channel senders. Without WhatsApp/SMTP credentials the app runs in test mode: nothing leaves the building."""

import smtplib
import uuid
from dataclasses import dataclass
from email.message import EmailMessage

import httpx

from app.config import get_settings
from app.models import Campaign, Contact
from app.phone import wa_id

PLACEHOLDERS = ("first_name", "name", "city", "company", "last_route")


def render(template: str, contact: Contact) -> str:
    values = {
        "first_name": contact.first_name or "there",
        "name": contact.name or "there",
        "city": contact.city or "",
        "company": contact.company or "",
        "last_route": (contact.last_route or "").replace("-", " "),
    }
    out = template or ""
    for key in PLACEHOLDERS:
        out = out.replace("{" + key + "}", values[key])
    return out


@dataclass
class SendResult:
    ok: bool
    message_id: str | None = None
    error: str = ""


class Sender:
    test_mode = False

    def send(self, contact: Contact, campaign: Campaign, body: str) -> SendResult:
        raise NotImplementedError


class TestModeSender(Sender):
    test_mode = True

    def send(self, contact: Contact, campaign: Campaign, body: str) -> SendResult:
        return SendResult(ok=True, message_id=f"test-{uuid.uuid4().hex[:16]}")


class WhatsAppSender(Sender):
    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.url = f"https://graph.facebook.com/{s.wa_api_version}/{s.wa_phone_number_id}/messages"
        self.client = client or httpx.Client(timeout=20, headers={"Authorization": f"Bearer {s.wa_token}"})

    @staticmethod
    def payload(contact: Contact, campaign: Campaign, body: str) -> dict:
        msg: dict = {"messaging_product": "whatsapp", "recipient_type": "individual", "to": wa_id(contact.phone or "")}
        media = campaign.media_type if campaign.media_url and campaign.media_type in {"image", "video", "document"} else ""
        if campaign.wa_template_name:
            components = []
            if media:
                components.append({"type": "header", "parameters": [{"type": media, media: {"link": campaign.media_url}}]})
            if campaign.wa_template_params:
                params = [{"type": "text", "text": render("{" + p + "}", contact) or "-"} for p in campaign.wa_template_params]
                components.append({"type": "body", "parameters": params})
            msg |= {"type": "template", "template": {
                "name": campaign.wa_template_name, "language": {"code": campaign.wa_template_lang or "en"},
                **({"components": components} if components else {}),
            }}
        elif media:
            item: dict = {"link": campaign.media_url}
            if body:
                item["caption"] = body
            msg |= {"type": media, media: item}
        else:
            msg |= {"type": "text", "text": {"body": body, "preview_url": True}}
        return msg

    def send(self, contact: Contact, campaign: Campaign, body: str) -> SendResult:
        try:
            r = self.client.post(self.url, json=self.payload(contact, campaign, body))
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Network error: {exc}"[:500])
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code >= 400 or "error" in data:
            err = data.get("error", {})
            return SendResult(ok=False, error=f"{err.get('code', r.status_code)}: {err.get('message', r.text)}"[:500])
        return SendResult(ok=True, message_id=data["messages"][0]["id"])


class EmailSender(Sender):
    def send(self, contact: Contact, campaign: Campaign, body: str) -> SendResult:
        s = get_settings()
        msg = EmailMessage()
        msg["From"], msg["To"] = s.smtp_from or s.smtp_user, contact.email
        msg["Subject"] = render(campaign.subject, contact) or campaign.name
        text = body + (f"\n\n{campaign.media_url}" if campaign.media_url else "")
        msg.set_content(text + "\n\n—\nKamilight Global Logistics. Reply STOP to stop receiving these emails.")
        try:
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password)
                smtp.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            return SendResult(ok=False, error=str(exc)[:500])
        return SendResult(ok=True, message_id=f"email-{uuid.uuid4().hex[:16]}")


def channel_live(channel: str) -> bool:
    s = get_settings()
    if channel == "whatsapp":
        return bool(s.wa_token and s.wa_phone_number_id)
    if channel == "email":
        return bool(s.smtp_host)
    return False


def get_sender(channel: str) -> Sender:
    if not channel_live(channel):
        return TestModeSender()
    return WhatsAppSender() if channel == "whatsapp" else EmailSender()
