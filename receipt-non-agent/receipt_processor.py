"""Extract receipt data from images using Claude Vision."""

import base64
import json
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path

from anthropic import AsyncAnthropic
from anthropic.types import Base64ImageSourceParam, ImageBlockParam, TextBlockParam

from config import config

SYSTEM_PROMPT = (
    "You are a receipt data extraction assistant. Analyze the receipt image and extract "
    "the following fields as a JSON object. Return ONLY valid JSON, no markdown fencing "
    "or explanation.\n\n"
    "Fields:\n"
    "- date: string in DD/MM/YYYY format (European date format)\n"
    '- amount: string with numeric value (e.g. "42.50")\n'
    '- currency: string ISO currency code (e.g. "EUR", "USD", "GBP")\n'
    "- expense_type: one of: Meals, Transport, Office Supplies, Software, Accommodation, Utilities, Other\n"
    "- merchant: string name of the merchant/vendor\n"
    "- description: string brief description of the purchase\n\n"
    "Example output:\n"
    '{"date": "14/03/2026", "amount": "42.50", "currency": "EUR", '
    '"expense_type": "Meals", "merchant": "Restaurant XYZ", "description": "Team lunch"}'
)


@dataclass
class ReceiptData:
    """Extracted receipt data."""

    date: str
    amount: str
    currency: str
    expense_type: str
    merchant: str
    description: str


async def extract_receipt(image_path: str) -> ReceiptData:
    """Extract receipt data from an image using Claude Vision."""
    path = Path(image_path)
    mime_type: str = mimetypes.guess_type(str(path))[0] or "image/jpeg"

    with open(path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    client = AsyncAnthropic(api_key=config.anthropic_api_key)

    content: list[ImageBlockParam | TextBlockParam] = [
        ImageBlockParam(
            type="image",
            source=Base64ImageSourceParam(type="base64", media_type=mime_type, data=image_data),  # type: ignore[arg-type]
        ),
        TextBlockParam(type="text", text="Extract the receipt data from this image."),
    ]

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )

    raw = response.content[0].text  # type: ignore[union-attr]
    # Strip markdown fencing if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    data = json.loads(cleaned)

    return ReceiptData(
        date=data["date"],
        amount=data["amount"],
        currency=data["currency"],
        expense_type=data["expense_type"],
        merchant=data["merchant"],
        description=data["description"],
    )
