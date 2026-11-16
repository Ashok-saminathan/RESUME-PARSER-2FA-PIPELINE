"""Deliver OTPs by email (SMTP) or WhatsApp (Meta Cloud API). Uses only the standard library.

In development, with no provider configured, the message is logged to the console instead.
In production a missing provider is an error.
"""
import asyncio
import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage

from app.config import get_settings

logger = logging.getLogger("onboarding.notify")


class DeliveryError(Exception):
    pass


def mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_phone(phone: str) -> str:
    return f"{phone[:3]}******{phone[-2:]}"


def _send_email_sync(to: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
        smtp.starttls()
        if s.smtp_user:
            smtp.login(s.smtp_user, s.smtp_password)
        smtp.send_message(msg)


def _send_whatsapp_sync(to_e164: str, code: str) -> None:
    s = get_settings()
    # Meta authentication templates carry the code in the body and in the copy-code button.
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164.lstrip("+"),
        "type": "template",
        "template": {
            "name": s.whatsapp_template_name,
            "language": {"code": "en"},
            "components": [
                {"type": "body", "parameters": [{"type": "text", "text": code}]},
                {"type": "button", "sub_type": "url", "index": "0",
                 "parameters": [{"type": "text", "text": code}]},
            ],
        },
    }
    request = urllib.request.Request(
        f"https://graph.facebook.com/v20.0/{s.whatsapp_phone_number_id}/messages",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {s.whatsapp_token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status >= 300:
            raise DeliveryError(f"WhatsApp API returned {response.status}")


async def send_email_otp(to: str, code: str, ttl_seconds: int) -> None:
    s = get_settings()
    if not s.smtp_host:
        if s.is_production:
            raise DeliveryError("Email provider is not configured")
        logger.warning("[dev] email OTP for %s: %s", mask_email(to), code)
        return
    minutes = max(1, ttl_seconds // 60)
    body = f"Your verification code is {code}. It expires in {minutes} minutes. Do not share it with anyone."
    try:
        await asyncio.to_thread(_send_email_sync, to, "Your verification code", body)
    except Exception as exc:
        raise DeliveryError("Could not send the email") from exc


async def send_whatsapp_otp(to_e164: str, code: str) -> None:
    s = get_settings()
    if not (s.whatsapp_token and s.whatsapp_phone_number_id):
        if s.is_production:
            raise DeliveryError("WhatsApp provider is not configured")
        logger.warning("[dev] WhatsApp OTP for %s: %s", mask_phone(to_e164), code)
        return
    try:
        await asyncio.to_thread(_send_whatsapp_sync, to_e164, code)
    except Exception as exc:
        raise DeliveryError("Could not send the WhatsApp message") from exc
