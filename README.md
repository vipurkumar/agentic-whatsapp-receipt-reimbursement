# Agentic WhatsApp Receipt Reimbursement System

A WhatsApp-based receipt processing system that extracts data from receipt photos, logs expenses, sends reimbursement emails, and responds to natural language queries — all via WhatsApp.

Built with Python, FastAPI, Claude Vision, Twilio, and openpyxl.

## Two Versions

### [`receipt-non-agent/`](./receipt-non-agent/) — Pipeline Version

A hardcoded sequential pipeline:

```
Receipt photo → Download → Extract (Claude Vision) → Dedupe → Log → Email → Confirm
```

- Handles receipt photos only
- Fixed processing order
- Simple and predictable

### [`receipt-agent-agentic/`](./receipt-agent-agentic/) — Agentic Version

Claude orchestrates the entire flow using **tool_use**, deciding what tools to call based on the user's message:

```
User message → Claude Agent → [tool calls] → Response
```

- Receipt processing (same as pipeline, but Claude-driven)
- Natural language queries: "total spending this month", "show all meals"
- Deletions: "delete receipt #3"
- Custom reports: "send report to manager@company.com"
- Smart handling: blurry photos, non-receipt images, off-topic messages

#### 7 Tools Available to Claude

| Tool | Description |
|------|-------------|
| `extract_receipt` | Claude Vision extraction from receipt image |
| `check_duplicate` | Check if receipt already logged |
| `log_receipt` | Save to Excel with image path |
| `send_email` | Reimbursement or custom report email with attachments |
| `query_expenses` | Query by month, type, merchant, etc. |
| `delete_receipt` | Remove receipt and re-number |
| `send_whatsapp` | Reply to user (always final action) |

## Tech Stack

- **Python 3.12** + **FastAPI** — webhook server
- **Claude Vision** (Anthropic API) — receipt data extraction
- **Claude tool_use** (agentic version) — orchestration
- **Twilio** — WhatsApp messaging
- **openpyxl** — Excel expense logging
- **smtplib** — reimbursement emails

## Quick Start

```bash
cd receipt-agent-agentic  # or receipt-agent

# Install dependencies
pip install -r requirements.txt

# Copy and fill in your credentials
cp .env.example .env

# Start the server
make run

# Test locally (agentic version)
python test_local.py --image receipts/test_receipt.png
python test_local.py --text "total spending this month"

# Run mocked pipeline tests
python test_pipeline.py
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude |
| `AGENT_MODEL` | Claude model (agentic version only) |
| `TWILIO_ACCOUNT_SID` | Twilio account SID |
| `TWILIO_AUTH_TOKEN` | Twilio auth token |
| `TWILIO_WHATSAPP_NUMBER` | Twilio WhatsApp sender number |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | Email configuration |
| `REIMBURSEMENT_EMAIL` | Default recipient for reimbursement emails |

See `.env.example` in each folder for the full list.

## Architecture

### Pipeline Version Flow

```
WhatsApp Photo → Twilio Webhook → Download Image → Claude Vision Extract
→ Duplicate Check → Log to Excel → Send Email → WhatsApp Confirmation
```

### Agentic Version Flow

```
WhatsApp Message (text/photos) → Twilio Webhook → Download Images
→ Claude Agent Loop (max 20 iterations):
    → Claude sees message + images
    → Claude decides which tools to call
    → Tools execute concurrently
    → Results fed back to Claude
    → Repeat until done
→ Final: send_whatsapp confirmation
```
