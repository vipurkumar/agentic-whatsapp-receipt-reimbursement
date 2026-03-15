"""End-to-end pipeline test with mocked external services."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

from receipt_processor import ReceiptData, extract_receipt

FAKE_CLAUDE_RESPONSE = json.dumps({
    "date": "14/03/2026",
    "amount": "51.43",
    "currency": "EUR",
    "expense_type": "Meals",
    "merchant": "Cafe de Amsterdam",
    "description": "Breakfast with cappuccinos, croissant, juice, eggs benedict and pancakes",
})

IMAGE_PATH = "receipts/test_receipt.png"


async def test_extract() -> ReceiptData:
    """Test receipt extraction with mocked Claude API."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=FAKE_CLAUDE_RESPONSE)]

    with patch("receipt_processor.AsyncAnthropic") as mock_anthropic:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_message)
        mock_anthropic.return_value = mock_client

        data = await extract_receipt(IMAGE_PATH)

    print(f"  Date:         {data.date}")
    print(f"  Merchant:     {data.merchant}")
    print(f"  Amount:       {data.amount} {data.currency}")
    print(f"  Expense Type: {data.expense_type}")
    print(f"  Description:  {data.description}")
    return data


def test_sheets_log(data: ReceiptData) -> int:
    """Test sheets logging with mocked gspread."""
    with patch("sheets_logger._get_client") as mock_get_client:
        mock_ws = MagicMock()
        mock_ws.get_all_values.return_value = [["header"]]  # 1 row = headers exist
        mock_ws.append_row.return_value = None

        mock_spreadsheet = MagicMock()
        mock_spreadsheet.sheet1 = mock_ws

        mock_client = MagicMock()
        mock_client.open_by_key.return_value = mock_spreadsheet
        mock_get_client.return_value = mock_client

        # Temporarily set a sheet ID so it uses open_by_key
        import config
        original = config.config.google_sheet_id
        config.config.google_sheet_id = "fake-sheet-id"

        from sheets_logger import append_receipt
        seq = append_receipt(data)

        config.config.google_sheet_id = original

    print(f"  Logged as entry #{seq}")

    # Verify append_row was called with correct data
    call_args = mock_ws.append_row.call_args
    row = call_args[0][0]
    print(f"  Row data: {row}")
    assert row[1] == "14/03/2026", f"Date mismatch: {row[1]}"
    assert row[2] == "Cafe de Amsterdam", f"Merchant mismatch: {row[2]}"
    assert row[4] == "51.43", f"Amount mismatch: {row[4]}"
    return seq


def test_email(data: ReceiptData, seq: int) -> None:
    """Test email sending with mocked SMTP."""
    with patch("email_sender.smtplib.SMTP") as mock_smtp_class:
        mock_server = MagicMock()
        mock_smtp_class.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_class.return_value.__exit__ = MagicMock(return_value=False)

        from email_sender import send_reimbursement_email
        send_reimbursement_email(data, IMAGE_PATH, seq)

    print("  Email composed and 'sent' (mocked)")

    # Verify SMTP interactions
    mock_server.starttls.assert_called_once()
    mock_server.login.assert_called_once()
    mock_server.send_message.assert_called_once()

    msg = mock_server.send_message.call_args[0][0]
    print(f"  Subject: {msg['Subject']}")
    print(f"  Attachments: {len(msg.get_payload()) - 1} file(s)")


async def test_whatsapp_reply(data: ReceiptData, seq: int) -> None:
    """Test WhatsApp reply with mocked httpx."""
    with patch("whatsapp_client.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(json=lambda: {"sid": "SM_test"}))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        from whatsapp_client import send_text_message
        confirmation = (
            f"Receipt #{seq} logged!\n"
            f"Merchant: {data.merchant}\n"
            f"Amount: {data.amount} {data.currency}"
        )
        await send_text_message("+31612345678", confirmation)

    print("  WhatsApp confirmation 'sent' (mocked)")
    call_args = mock_client.post.call_args
    body = call_args[1]["data"]["Body"]
    print(f"  Message preview: {body[:60]}...")


async def main() -> None:
    """Run full pipeline test."""
    print("=" * 50)
    print("PIPELINE TEST — receipts/test_receipt.png")
    print("=" * 50)

    print("\n[1/4] Extract receipt data (Claude Vision mock)...")
    data = await test_extract()

    print("\n[2/4] Log to Google Sheets (gspread mock)...")
    seq = test_sheets_log(data)

    print("\n[3/4] Send email (SMTP mock)...")
    test_email(data, seq)

    print("\n[4/4] Send WhatsApp confirmation (httpx mock)...")
    await test_whatsapp_reply(data, seq)

    print("\n" + "=" * 50)
    print("ALL 4 PIPELINE STAGES PASSED")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
