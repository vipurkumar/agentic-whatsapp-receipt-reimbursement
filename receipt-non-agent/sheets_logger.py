"""Log receipt data to Google Sheets."""

from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

from config import config
from receipt_processor import ReceiptData

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADERS = ["#", "Date", "Merchant", "Expense Type", "Amount", "Currency", "Description", "Logged At"]

_client: gspread.Client | None = None


def _get_client() -> gspread.Client:
    """Lazy-initialize gspread client."""
    global _client
    if _client is not None:
        return _client

    creds_info = config.get_google_credentials_info()
    if creds_info is None:
        raise ValueError("Google service account credentials not configured")

    credentials = Credentials.from_service_account_info(creds_info, scopes=SCOPES)
    _client = gspread.authorize(credentials)
    return _client


def _get_or_create_spreadsheet(client: gspread.Client) -> gspread.Spreadsheet:
    """Open existing spreadsheet or create a new one with styled headers."""
    if config.google_sheet_id:
        return client.open_by_key(config.google_sheet_id)

    spreadsheet = client.create(config.google_sheet_name)

    if config.google_sheet_share_email:
        spreadsheet.share(config.google_sheet_share_email, perm_type="user", role="writer")

    worksheet = spreadsheet.sheet1
    worksheet.update([HEADERS], range_name="A1:H1", value_input_option=gspread.utils.ValueInputOption.user_entered)

    # Style headers with orange background
    worksheet.format(
        "A1:H1",
        {
            "backgroundColor": {"red": 1.0, "green": 0.6, "blue": 0.0},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1.0, "green": 1.0, "blue": 1.0}},
        },
    )

    return spreadsheet


def append_receipt(data: ReceiptData) -> int:
    """Append receipt data to Google Sheet. Returns the sequence number."""
    client = _get_client()
    spreadsheet = _get_or_create_spreadsheet(client)
    worksheet = spreadsheet.sheet1

    all_values = worksheet.get_all_values()
    seq_number = len(all_values)  # Row count minus header = sequence, but len includes header so it's next seq

    if len(all_values) == 0:
        # No headers yet, add them
        worksheet.update([HEADERS], range_name="A1:H1", value_input_option=gspread.utils.ValueInputOption.user_entered)
        seq_number = 1

    timestamp = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    row = [
        seq_number,
        data.date,
        data.merchant,
        data.expense_type,
        data.amount,
        data.currency,
        data.description,
        timestamp,
    ]

    worksheet.append_row(row, value_input_option=gspread.utils.ValueInputOption.user_entered)
    return seq_number
