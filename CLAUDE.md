# Agentic WhatsApp Receipt Reimbursement System

## Overview

Receipt processing system that extracts data from receipt photos, logs expenses to Excel, sends reimbursement emails, and answers natural language queries.

**Two usage modes:**
- **Claude Code Skill** — Use `/omni1-reimbursement-agentic-skill` to process receipts directly from a folder. No WhatsApp/Twilio needed. Claude reads images, extracts data, and calls the Python modules.
- **WhatsApp Bot** — Users send receipts via WhatsApp. Claude agent orchestrates the full flow via Twilio webhooks.

**Two implementations:**
- `receipt-agent-agentic/` — Claude-powered agentic version (main). Claude orchestrates workflows using tool_use.
- `receipt-non-agent/` — Hardcoded sequential pipeline for receipt processing only.

## Tech Stack

Python 3.12, FastAPI, Anthropic Claude API (Vision + tool_use), Twilio WhatsApp (optional), openpyxl (Excel), smtplib (SMTP).

## Development Commands

All commands run from `receipt-agent-agentic/`:

```bash
make run              # Start FastAPI server (port 8000)
make install          # Install deps + ruff + pyright
make lint             # ruff check .
make format           # ruff format .
make typecheck        # pyright
python test_pipeline.py   # Mocked pipeline tests
python test_local.py --image receipts/test.png   # Local test with image
python test_local.py --text "total spending this month"  # Local text query
```

## Code Conventions

- Python 3.12, async/await throughout
- Ruff linting: rules E, F, I, N, UP, B, SIM, TCH — line-length 120
- Pyright: basic mode
- Sync functions wrapped with `asyncio.to_thread()` when called from async context
- Type hints on all function signatures

## Environment Setup

```bash
cd receipt-agent-agentic
cp .env.example .env
# Fill in: ANTHROPIC_API_KEY, TWILIO_*, SMTP_*, REIMBURSEMENT_EMAIL
```

## Architecture (Agentic Version)

```
WhatsApp Message → Twilio Webhook (main.py) → Download Images
→ Agent Loop (agent.py, max 20 iterations):
    → Claude sees message + base64 images
    → Claude decides which tools to call
    → Tools execute concurrently via execute_tool() dispatcher (tools.py)
    → Results fed back to Claude
→ Final: send_whatsapp confirmation
```

Key files:
- `main.py` — FastAPI webhook server with 5-second debounce for batch images
- `agent.py` — Agentic loop orchestrator
- `tools.py` — 7 tool schemas (TOOL_SCHEMAS) + execute_tool() dispatcher
- `config.py` — Environment variable config loader (Config dataclass)
- `receipt_processor.py` — Claude Vision extraction (ReceiptData dataclass)
- `excel_logger.py` — Receipt CRUD (append, query, delete, duplicate check, summary)
- `email_sender.py` — SMTP reimbursement & custom report emails
- `whatsapp_client.py` — Twilio media download & message sending
