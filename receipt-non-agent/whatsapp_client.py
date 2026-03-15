"""Twilio WhatsApp API client for media download and messaging."""

import uuid
from pathlib import Path

import httpx

from config import config

TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"


def _auth() -> tuple[str, str]:
    """Return Twilio Basic Auth credentials."""
    return (config.twilio_account_sid, config.twilio_auth_token)


async def download_media(media_url: str, save_dir: str) -> str:
    """Download media from a Twilio media URL. Returns the saved file path."""
    async with httpx.AsyncClient() as client:
        response = await client.get(media_url, auth=_auth(), follow_redirects=True)
        response.raise_for_status()

        content_type = response.headers.get("content-type", "image/jpeg")
        ext_map = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
            "application/pdf": ".pdf",
        }
        ext = ext_map.get(content_type, ".jpg")

        save_path = Path(save_dir) / f"{uuid.uuid4()}{ext}"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(response.content)

        return str(save_path)


async def send_text_message(to: str, body: str) -> dict:
    """Send a text message via Twilio WhatsApp API."""
    url = f"{TWILIO_API_BASE}/{config.twilio_account_sid}/Messages.json"

    # Ensure whatsapp: prefix on recipient
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"

    payload = {
        "From": config.twilio_whatsapp_number,
        "To": to,
        "Body": body,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=payload, auth=_auth())
        response.raise_for_status()
        return response.json()
