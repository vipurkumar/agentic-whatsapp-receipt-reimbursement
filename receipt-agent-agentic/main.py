"""FastAPI server for agentic WhatsApp receipt reimbursement webhook."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

from agent import run_agent
from config import config
from whatsapp_client import download_media

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Debounce buffer: sender -> {text, media_urls}
BATCH_DELAY = 5  # seconds
_pending: dict[str, dict] = {}
_pending_tasks: dict[str, asyncio.Task] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: ensure receipts directory exists."""
    Path(config.receipts_dir).mkdir(parents=True, exist_ok=True)
    logger.info("Agentic reimbursement server started on %s:%s", config.host, config.port)
    yield
    logger.info("Agentic reimbursement server shutting down")


app = FastAPI(title="Agentic WhatsApp Reimbursement", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/webhook")
async def receive_webhook(request: Request) -> PlainTextResponse:
    """Handle incoming Twilio WhatsApp messages."""
    form = await request.form()

    num_media = int(str(form.get("NumMedia", "0")))
    sender = str(form.get("From", ""))
    body = str(form.get("Body", "")).strip()

    # Strip whatsapp: prefix for internal use
    if sender.startswith("whatsapp:"):
        sender = sender[len("whatsapp:"):]

    # Text-only messages: process immediately (no debounce)
    if num_media == 0 and body:
        logger.info("Text message from %s: %s", sender, body[:100])
        asyncio.create_task(_process_text(sender, body))
        return PlainTextResponse(content="<Response></Response>", media_type="text/xml")

    # Image messages: debounce to batch multiple photos
    if sender not in _pending:
        _pending[sender] = {"text": body, "media_urls": []}
    elif body and not _pending[sender]["text"]:
        _pending[sender]["text"] = body

    for i in range(num_media):
        media_url = str(form.get(f"MediaUrl{i}", ""))
        if media_url:
            _pending[sender]["media_urls"].append(media_url)
            logger.info("Buffered image from %s (%d pending)", sender, len(_pending[sender]["media_urls"]))

    # Cancel existing timer and restart
    if sender in _pending_tasks:
        _pending_tasks[sender].cancel()
    _pending_tasks[sender] = asyncio.create_task(_debounce_process(sender))

    return PlainTextResponse(content="<Response></Response>", media_type="text/xml")


async def _process_text(sender: str, text: str) -> None:
    """Process a text-only message through the agent."""
    try:
        await run_agent(sender=sender, text=text)
    except Exception:
        logger.exception("Agent failed for text message from %s", sender)
        try:
            from whatsapp_client import send_text_message

            await send_text_message(sender, "Sorry, something went wrong. Please try again.")
        except Exception:
            logger.exception("Failed to send error message to %s", sender)


async def _debounce_process(sender: str) -> None:
    """Wait for BATCH_DELAY seconds, then process all buffered media for this sender."""
    await asyncio.sleep(BATCH_DELAY)

    pending = _pending.pop(sender, None)
    _pending_tasks.pop(sender, None)

    if not pending:
        return

    media_urls = pending["media_urls"]
    text = pending["text"]

    if not media_urls:
        return

    logger.info("Batch processing %d image(s) from %s", len(media_urls), sender)

    try:
        # Download all images concurrently
        image_paths = await asyncio.gather(*[download_media(url, config.receipts_dir) for url in media_urls])
        logger.info("Downloaded %d images", len(image_paths))

        # Run agent with images and optional text
        await run_agent(sender=sender, text=text or None, image_paths=list(image_paths))

    except Exception:
        logger.exception("Agent failed for image message from %s", sender)
        try:
            from whatsapp_client import send_text_message

            await send_text_message(sender, "Sorry, I couldn't process that. Please try again.")
        except Exception:
            logger.exception("Failed to send error message to %s", sender)


if __name__ == "__main__":
    uvicorn.run("main:app", host=config.host, port=config.port, reload=True)
