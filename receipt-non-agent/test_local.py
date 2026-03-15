"""Local test script: extract -> sheets -> email pipeline without WhatsApp."""

import asyncio
import sys

from email_sender import send_reimbursement_email
from receipt_processor import extract_receipt
from sheets_logger import append_receipt


async def main(image_path: str) -> None:
    """Run the receipt processing pipeline on a local image."""
    print(f"Processing: {image_path}")

    print("Extracting receipt data...")
    receipt_data = await extract_receipt(image_path)
    print(f"  Date:     {receipt_data.date}")
    print(f"  Merchant: {receipt_data.merchant}")
    print(f"  Amount:   {receipt_data.amount} {receipt_data.currency}")
    print(f"  Type:     {receipt_data.expense_type}")
    print(f"  Desc:     {receipt_data.description}")

    print("Logging to Google Sheets...")
    seq_number = append_receipt(receipt_data)
    print(f"  Entry #{seq_number}")

    print("Sending email...")
    send_reimbursement_email(receipt_data, image_path, seq_number)
    print("  Sent!")

    print("Done!")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <image_path>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
