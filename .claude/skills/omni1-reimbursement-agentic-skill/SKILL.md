---
name: omni1-reimbursement-agentic-skill
description: Process receipts, query expenses, and manage reimbursements via WhatsApp. Use when working with the agentic receipt reimbursement system.
user-invocable: true
argument-hint: [action or question]
---

# Agentic WhatsApp Receipt Reimbursement Skill

You are assisting with a WhatsApp-based receipt reimbursement system powered by Claude. The system processes receipt photos, logs expenses to Excel, sends reimbursement emails, and answers natural language queries — all via WhatsApp.

## System Architecture

```
WhatsApp Message → Twilio Webhook (main.py) → Download Images
→ Agent Loop (agent.py, max 20 iterations):
    → Claude sees message + base64-encoded images
    → Claude decides which tools to call
    → Tools execute concurrently via execute_tool() in tools.py
    → Results fed back to Claude
→ Final: send_whatsapp confirmation
```

## 7 Available Tools

All tools are defined in `receipt-agent-agentic/tools.py` as `TOOL_SCHEMAS` and dispatched by `execute_tool()`.

### 1. `extract_receipt`
Extract structured data from a receipt image using Claude Vision.
- **Input**: `image_path` (string, required) — local file path to receipt image
- **Output**: `{success, date, amount, currency, expense_type, merchant, description}`
- **Implementation**: `receipt_processor.py` → `extract_receipt()` (async)

### 2. `check_duplicate`
Check if a receipt with matching date, merchant, and amount already exists.
- **Input**: `date` (DD/MM/YYYY), `merchant`, `amount` (all required)
- **Output**: `{is_duplicate: bool}`
- **Implementation**: `excel_logger.py` → `is_duplicate()` (sync)

### 3. `log_receipt`
Save a receipt to the Excel reimbursement file. Returns assigned sequence number.
- **Input**: `date`, `amount`, `currency`, `expense_type`, `merchant`, `description` (all required), `image_path` (optional)
- **Output**: `{seq_number: int}`
- **Implementation**: `excel_logger.py` → `append_receipt()` (sync)

### 4. `send_email`
Send reimbursement or custom report emails with attachments.
- **Input**: `receipts` (array of receipt objects), `to` (optional custom recipient), `subject` (optional), `body` (optional)
- **Behavior**: If `subject` + `body` provided → custom report via `send_summary_email()`. If `receipts` provided → standard reimbursement via `send_reimbursement_email()`.
- **Implementation**: `email_sender.py` (sync, wrapped with `asyncio.to_thread`)

### 5. `query_expenses`
Query logged receipts with filters. Returns matching receipts and totals by currency.
- **Input**: `filter_type` (required, enum: all/month/expense_type/last_n/merchant/summary), `filter_value` (optional)
- **Output**: `{count, receipts, totals}` or summary dict
- **Implementation**: `excel_logger.py` → `query_receipts()` / `get_summary()` (sync)

### 6. `delete_receipt`
Remove a receipt by sequence number. Remaining receipts are re-numbered.
- **Input**: `seq_number` (integer, required)
- **Output**: `{deleted: bool}`
- **Implementation**: `excel_logger.py` → `delete_receipt()` (sync)

### 7. `send_whatsapp`
Send a WhatsApp message to the user. Always the final action in any flow.
- **Input**: `to` (phone number, required), `message` (text, required)
- **Output**: `{sent: bool}`
- **Implementation**: `whatsapp_client.py` → `send_text_message()` (async)

## Standard Workflows

### Processing a Receipt
1. `extract_receipt` → get structured data from image
2. `check_duplicate` → verify not already logged
3. `log_receipt` → save to Excel (if not duplicate)
4. `send_email` → email reimbursement with attachment
5. `send_whatsapp` → confirm to user

### Querying Expenses
1. `query_expenses` → filter by month/type/merchant/etc.
2. `send_whatsapp` → reply with formatted results

### Deleting a Receipt
1. `delete_receipt` → remove by sequence number
2. `send_whatsapp` → confirm deletion

### Batch Processing (Multiple Images)
- `main.py` debounces for 5 seconds to batch images sent rapidly
- All images processed in single agent run
- Single batched email sent for all receipts

## Key Files

| File | Purpose |
|------|---------|
| `receipt-agent-agentic/main.py` | FastAPI webhook server, image debouncing |
| `receipt-agent-agentic/agent.py` | Agentic loop (Claude + tool calls, max 20 iterations) |
| `receipt-agent-agentic/tools.py` | Tool schemas (`TOOL_SCHEMAS`) and `execute_tool()` dispatcher |
| `receipt-agent-agentic/config.py` | `Config` dataclass, env var loading via dotenv |
| `receipt-agent-agentic/receipt_processor.py` | `ReceiptData` dataclass, Claude Vision extraction |
| `receipt-agent-agentic/excel_logger.py` | Excel CRUD: append, query, delete, duplicate check, summary |
| `receipt-agent-agentic/email_sender.py` | SMTP email: reimbursement + custom reports |
| `receipt-agent-agentic/whatsapp_client.py` | Twilio: media download + message sending |
| `receipt-agent-agentic/test_local.py` | CLI for local testing (supports `--dry-run`) |
| `receipt-agent-agentic/test_pipeline.py` | Mocked pipeline tests |

## Development Guide

### Adding a New Tool
1. Add schema dict to `TOOL_SCHEMAS` in `tools.py` (name, description, input_schema)
2. Add handler branch in `execute_tool()` in `tools.py`
3. Implement the actual logic in the appropriate module
4. Update the system prompt in `agent.py` → `_build_system_prompt()` to describe the new tool

### Running and Testing
```bash
cd receipt-agent-agentic
make run                # Start server on port 8000
make lint               # ruff check
make format             # ruff format
make typecheck          # pyright
python test_pipeline.py # Run mocked tests
python test_local.py --image path/to/receipt.png  # Test with real image
python test_local.py --text "show all expenses"   # Test text query
```

### Code Conventions
- Python 3.12, async/await
- Ruff: line-length 120, rules E, F, I, N, UP, B, SIM, TCH
- Pyright: basic mode
- Sync functions wrapped with `asyncio.to_thread()` in async context
- Type hints on all signatures
