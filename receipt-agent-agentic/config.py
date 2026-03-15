"""Configuration loaded from environment variables."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration from environment variables."""

    # Twilio WhatsApp
    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_whatsapp_number: str = field(default_factory=lambda: os.getenv("TWILIO_WHATSAPP_NUMBER", ""))

    # Anthropic
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    agent_model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "claude-sonnet-4-20250514"))

    # SMTP
    smtp_host: str = field(default_factory=lambda: os.getenv("SMTP_HOST", "smtp.gmail.com"))
    smtp_port: int = field(default_factory=lambda: int(os.getenv("SMTP_PORT", "587")))
    smtp_user: str = field(default_factory=lambda: os.getenv("SMTP_USER", ""))
    smtp_password: str = field(default_factory=lambda: os.getenv("SMTP_PASSWORD", ""))
    reimbursement_email: str = field(default_factory=lambda: os.getenv("REIMBURSEMENT_EMAIL", ""))

    # Google Sheets
    google_service_account_json: str = field(default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", ""))
    google_sheet_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_ID", ""))
    google_sheet_name: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_NAME", "Reimbursements"))
    google_sheet_share_email: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEET_SHARE_EMAIL", ""))

    # Storage
    receipts_dir: str = field(default_factory=lambda: os.getenv("RECEIPTS_DIR", "receipts"))

    # Server
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    def get_google_credentials_info(self) -> dict | None:
        """Parse Google service account credentials from file path or inline JSON."""
        value = self.google_service_account_json
        if not value:
            return None

        path = Path(value)
        if path.exists() and path.is_file():
            with open(path) as f:
                return json.load(f)

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None


config = Config()
