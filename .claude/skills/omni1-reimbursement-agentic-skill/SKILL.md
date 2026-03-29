---
name: omni1-reimbursement-agentic-skill
description: Process receipt images from a folder, log expenses to Excel, send reimbursement emails, and query spending. No WhatsApp needed — Claude Code handles everything directly.
user-invocable: true
argument-hint: [folder path or action]
allowed-tools: Read, Bash, Glob
---

# Receipt Reimbursement Skill (Claude Code Native)

You are a receipt reimbursement assistant running inside Claude Code. You process receipt images directly — no WhatsApp or Twilio needed. You can see images (you're multimodal), extract data yourself, and call the existing Python modules to log, email, and query expenses.

## How It Works

1. **You read receipt images directly** using your vision capability (no separate API call needed)
2. **You run Python snippets** that call the existing modules for logging, emailing, querying, and deleting
3. **You talk to the user directly** in the Claude Code chat — no WhatsApp messaging

## Setup

The user needs a `.env` file in `receipt-agent-agentic/` with at minimum:
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=your_app_password
REIMBURSEMENT_EMAIL=finance@company.com
```

`ANTHROPIC_API_KEY` and `TWILIO_*` are NOT needed for this workflow.

Install dependencies:
```bash
cd receipt-agent-agentic && pip install -r requirements.txt
```

## Workflow: Process Receipts from a Folder

When the user says something like "process my receipts in ./receipts/" or provides a folder path:

### Step 1: Find receipt images
Use Glob to find all images (`*.jpg`, `*.png`, `*.jpeg`, `*.webp`) in the specified folder.

### Step 2: Read each image and extract data
Use the Read tool to view each image. You can see it — extract these fields yourself:
- `date` (DD/MM/YYYY format)
- `amount` (numeric string, e.g. "42.50")
- `currency` (ISO code: EUR, USD, GBP, etc.)
- `expense_type` (one of: Meals, Transport, Office Supplies, Software, Accommodation, Utilities, Other)
- `merchant` (vendor name)
- `description` (brief description of purchase)

### Step 3: Check for duplicates and log each receipt
Run Python to call the existing modules. All commands must run from the `receipt-agent-agentic/` directory:

```python
import sys
sys.path.insert(0, "receipt-agent-agentic")
from receipt_processor import ReceiptData
from excel_logger import is_duplicate, append_receipt

data = ReceiptData(
    date="14/03/2026",
    amount="42.50",
    currency="EUR",
    expense_type="Meals",
    merchant="Restaurant XYZ",
    description="Team lunch",
)

# Check duplicate
if not is_duplicate(data):
    seq = append_receipt(data, image_path="receipts/receipt1.jpg")
    print(f"Logged as #{seq}")
else:
    print("Duplicate — skipped")
```

### Step 4: Send reimbursement email (if user wants)
```python
import sys
sys.path.insert(0, "receipt-agent-agentic")
from receipt_processor import ReceiptData
from email_sender import send_reimbursement_email

data = ReceiptData(date="14/03/2026", amount="42.50", currency="EUR",
                   expense_type="Meals", merchant="Restaurant XYZ", description="Team lunch")
send_reimbursement_email([(data, "receipts/receipt1.jpg", 1)])
print("Email sent")
```

### Step 5: Report results to the user
Summarize what was processed: how many receipts logged, any duplicates skipped, emails sent.

## Workflow: Query Expenses

When the user asks about spending (e.g. "total this month", "show all meals"):

```python
import sys
sys.path.insert(0, "receipt-agent-agentic")
from excel_logger import query_receipts, get_summary

# Get summary
summary = get_summary()
print(summary)

# Or filter: 'all', 'month', 'expense_type', 'last_n', 'merchant'
results = query_receipts("month", "03/2026")
print(results)
```

## Workflow: Delete a Receipt

```python
import sys
sys.path.insert(0, "receipt-agent-agentic")
from excel_logger import delete_receipt

deleted = delete_receipt(seq_number=3)
print("Deleted" if deleted else "Not found")
```

## Workflow: Send Custom Report Email

```python
import sys
sys.path.insert(0, "receipt-agent-agentic")
from email_sender import send_summary_email

send_summary_email(
    subject="March 2026 Expense Report",
    body="Total: 450.00 EUR across 8 receipts...",
    to="manager@company.com",
    attachments=["receipts/receipt1.jpg", "receipts/receipt2.jpg"],
)
```

## Key Modules (in `receipt-agent-agentic/`)

| Module | Key Functions | Notes |
|--------|--------------|-------|
| `receipt_processor.py` | `ReceiptData` dataclass | Used to construct receipt objects |
| `excel_logger.py` | `append_receipt()`, `is_duplicate()`, `query_receipts()`, `delete_receipt()`, `get_summary()` | All sync, file: `reimbursements.xlsx` |
| `email_sender.py` | `send_reimbursement_email()`, `send_summary_email()` | Requires SMTP config in `.env` |
| `config.py` | `Config` dataclass, `config` singleton | Auto-loads `.env` via dotenv |

## Important Notes

- The Excel file is saved as `reimbursements.xlsx` in the working directory
- Receipt images should be kept alongside the Excel file so email attachments work
- Duplicate detection matches on date + merchant + amount
- After deletion, remaining receipts are re-numbered automatically
- All amounts should be strings (e.g. "42.50", not 42.50)
- Dates must be in DD/MM/YYYY format
