"""Envío de correos por API web (Railway no deja usar SMTP fuera del plan Pro)."""
import logging
from email.utils import parseaddr

import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)


class ResendEmailBackend(BaseEmailBackend):
    url = "https://api.resend.com/emails"

    def send_messages(self, email_messages):
        sent = 0
        for msg in email_messages:
            payload = {
                "from": msg.from_email or settings.DEFAULT_FROM_EMAIL,
                "to": list(msg.to),
                "subject": msg.subject,
                "text": msg.body,
            }
            if msg.cc:
                payload["cc"] = list(msg.cc)
            if msg.bcc:
                payload["bcc"] = list(msg.bcc)
            if msg.reply_to:
                payload["reply_to"] = list(msg.reply_to)
            for content, mimetype in getattr(msg, "alternatives", []) or []:
                if mimetype == "text/html":
                    payload["html"] = content
            try:
                r = requests.post(
                    self.url,
                    json=payload,
                    headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
                    timeout=10,
                )
                r.raise_for_status()
                sent += 1
            except requests.RequestException as e:
                detail = getattr(getattr(e, "response", None), "text", "")
                # No se rompe el registro ni el login si el correo falla; queda en el log
                log.error("Resend no pudo enviar a %s: %s %s", payload["to"], e, detail)
                if not self.fail_silently and settings.DEBUG:
                    raise
        return sent


class BrevoEmailBackend(BaseEmailBackend):
    """Igual que el de Resend, pero con la API de Brevo."""

    url = "https://api.brevo.com/v3/smtp/email"

    def send_messages(self, email_messages):
        sent = 0
        for msg in email_messages:
            name, addr = parseaddr(msg.from_email or settings.DEFAULT_FROM_EMAIL)
            payload = {
                "sender": {"name": name or "Pancake", "email": addr},
                "to": [{"email": a} for a in msg.to],
                "subject": msg.subject,
                "textContent": msg.body,
            }
            if msg.reply_to:
                payload["replyTo"] = {"email": parseaddr(msg.reply_to[0])[1]}
            for content, mimetype in getattr(msg, "alternatives", []) or []:
                if mimetype == "text/html":
                    payload["htmlContent"] = content
            try:
                r = requests.post(
                    self.url,
                    json=payload,
                    headers={"api-key": settings.BREVO_API_KEY, "accept": "application/json"},
                    timeout=10,
                )
                r.raise_for_status()
                sent += 1
            except requests.RequestException as e:
                detail = getattr(getattr(e, "response", None), "text", "")
                log.error("Brevo no pudo enviar a %s: %s %s", msg.to, e, detail)
                if not self.fail_silently and settings.DEBUG:
                    raise
        return sent
