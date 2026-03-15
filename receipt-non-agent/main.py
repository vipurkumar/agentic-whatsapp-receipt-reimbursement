"""FastAPI server for WhatsApp receipt reimbursement webhook (Twilio)."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from config import config
from email_sender import send_reimbursement_email
from excel_logger import append_receipt, is_duplicate
from receipt_processor import extract_receipt
from whatsapp_client import download_media, send_text_message

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Debounce buffer: sender -> list of media URLs
# Waits BATCH_DELAY seconds after the last image before processing
BATCH_DELAY = 5  # seconds
_pending: dict[str, list[str]] = {}
_pending_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: ensure receipts directory exists."""
    Path(config.receipts_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Reimbursement agent started on %s:%s", config.host, config.port)
    yield
    logger.info("Reimbursement agent shutting down")


app = FastAPI(title="WhatsApp Reimbursement Agent", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(request: Request) -> PlainTextResponse:
    """Handle incoming Twilio WhatsApp messages."""
    form = await request.form()

    num_media = int(form.get("NumMedia", "0"))
    sender = str(form.get("From", ""))

    # Strip whatsapp: prefix for internal use
    if sender.startswith("whatsapp:"):
        sender = sender[len("whatsapp:"):]

    # Collect media URLs from this webhook
    for i in range(num_media):
        media_url = str(form.get(f"MediaUrl{i}", ""))
        if media_url:
            # Add to buffer
            if sender not in _pending:
                _pending[sender] = []
            _pending[sender].append(media_url)
            logger.info("Buffered image from %s (%d pending)", sender, len(_pending[sender]))

            # Cancel existing timer and restart
            if sender in _pending_tasks:
                _pending_tasks[sender].cancel()
            _pending_tasks[sender] = asyncio.create_task(_debounce_process(sender))

    # Return empty TwiML response
    return PlainTextResponse(content="<Response></Response>", media_type="text/xml")


async def _debounce_process(sender: str) -> None:
    """Wait for BATCH_DELAY seconds, then process all buffered images for this sender."""
    await asyncio.sleep(BATCH_DELAY)

    # Grab and clear the buffer
    media_urls = _pending.pop(sender, [])
    _pending_tasks.pop(sender, None)

    if media_urls:
        logger.info("Batch processing %d receipt(s) from %s", len(media_urls), sender)
        await _process_receipts(sender, media_urls)


async def _process_receipts(sender: str, media_urls: list[str]) -> None:
    """Process one or more receipt images from a single message."""
    try:
        # Download and extract all images concurrently
        async def _download_and_extract(media_url: str) -> tuple[str, object]:
            image_path = await download_media(media_url, config.receipts_dir)
            logger.info("Downloaded image to %s", image_path)
            receipt_data = await extract_receipt(image_path)
            logger.info("Extracted: %s %s at %s", receipt_data.amount, receipt_data.currency, receipt_data.merchant)
            return image_path, receipt_data

        results = await asyncio.gather(*[_download_and_extract(url) for url in media_urls])

        # Check duplicates, log new ones
        new_receipts = []  # (receipt_data, image_path, seq_number)
        duplicates = []
        for image_path, receipt_data in results:
            if is_duplicate(receipt_data):
                logger.info("Duplicate: %s %s at %s", receipt_data.amount, receipt_data.currency, receipt_data.merchant)
                Path(image_path).unlink(missing_ok=True)
                duplicates.append(receipt_data)
            else:
                seq_number = append_receipt(receipt_data)
                logger.info("Logged as entry #%d", seq_number)
                new_receipts.append((receipt_data, image_path, seq_number))

        # Send single email with all new receipts
        if new_receipts:
            send_reimbursement_email(new_receipts)
            logger.info("Email sent to %s with %d receipt(s)", config.reimbursement_email, len(new_receipts))

        # Build WhatsApp confirmation
        parts = []
        for data, _, seq in new_receipts:
            parts.append(
                f"Receipt #{seq} logged!\n"
                f"  Merchant: {data.merchant}\n"
                f"  Amount: {data.amount} {data.currency}\n"
                f"  Type: {data.expense_type}\n"
                f"  Date: {data.date}"
            )
        if duplicates:
            parts.append(f"{len(duplicates)} duplicate receipt(s) skipped.")

        if parts:
            confirmation = "\n\n".join(parts)
            if new_receipts:
                confirmation += f"\n\nEmail sent to {config.reimbursement_email}"
            await send_text_message(sender, confirmation)
            logger.info("Confirmation sent to %s", sender)

    except Exception:
        logger.exception("Failed to process receipts from %s", sender)
        try:
            await send_text_message(sender, "Sorry, I couldn't process that receipt. Please try again.")
        except Exception:
            logger.exception("Failed to send error message to %s", sender)


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port, reload=True)
