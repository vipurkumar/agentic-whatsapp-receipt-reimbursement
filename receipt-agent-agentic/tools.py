"""Tool schemas and execution dispatcher for the agentic receipt processor."""

import asyncio
import json
import logging
from typing import Any

from email_sender import send_reimbursement_email, send_summary_email
from excel_logger import append_receipt, delete_receipt, get_summary, is_duplicate, query_receipts
from receipt_processor import ReceiptData, extract_receipt
from whatsapp_client import send_text_message

logger = logging.getLogger(__name__)

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "extract_receipt",
        "description": (
            "Extract structured receipt data from an image file using Claude Vision. "
            "Returns date, amount, currency, expense_type, merchant, and description. "
            "Use this when the user sends a receipt photo."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Local file path to the receipt image.",
                },
            },
            "required": ["image_path"],
        },
    },
    {
        "name": "check_duplicate",
        "description": (
            "Check if a receipt with the given date, merchant, and amount already exists in the log. "
            "Use this after extracting receipt data and before logging, to avoid duplicates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Receipt date in DD/MM/YYYY format."},
                "merchant": {"type": "string", "description": "Merchant name."},
                "amount": {"type": "string", "description": "Receipt amount as string."},
            },
            "required": ["date", "merchant", "amount"],
        },
    },
    {
        "name": "log_receipt",
        "description": (
            "Log a receipt to the Excel reimbursement file. Returns the assigned sequence number. "
            "Only call this after checking for duplicates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Receipt date in DD/MM/YYYY format."},
                "amount": {"type": "string", "description": "Receipt amount."},
                "currency": {"type": "string", "description": "ISO currency code (EUR, USD, GBP, etc)."},
                "expense_type": {
                    "type": "string",
                    "description": (
                        "Category: Meals, Transport, Office Supplies, "
                        "Software, Accommodation, Utilities, or Other."
                    ),
                },
                "merchant": {"type": "string", "description": "Merchant name."},
                "description": {"type": "string", "description": "Brief description of the purchase."},
                "image_path": {"type": "string", "description": "Local file path to the receipt image."},
            },
            "required": ["date", "amount", "currency", "expense_type", "merchant", "description"],
        },
    },
    {
        "name": "send_email",
        "description": (
            "Send a reimbursement email with receipt details and image attachments. "
            "Can send to the default reimbursement email or a custom recipient. "
            "For standard receipts, provide receipt entries. For custom reports, provide subject and body."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "receipts": {
                    "type": "array",
                    "description": (
                        "List of receipt objects with fields: date, amount, currency, "
                        "expense_type, merchant, description, image_path, seq_number."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "amount": {"type": "string"},
                            "currency": {"type": "string"},
                            "expense_type": {"type": "string"},
                            "merchant": {"type": "string"},
                            "description": {"type": "string"},
                            "image_path": {"type": "string"},
                            "seq_number": {"type": "integer"},
                        },
                    },
                },
                "to": {
                    "type": "string",
                    "description": "Optional custom recipient email address(es), comma-separated.",
                },
                "subject": {
                    "type": "string",
                    "description": "Optional custom subject for summary/report emails.",
                },
                "body": {
                    "type": "string",
                    "description": "Optional custom body for summary/report emails.",
                },
            },
        },
    },
    {
        "name": "query_expenses",
        "description": (
            "Query logged receipts/expenses with filters. Returns matching receipts and totals. "
            "Use this when the user asks about spending, totals, or wants to see their receipts."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "filter_type": {
                    "type": "string",
                    "enum": ["all", "month", "expense_type", "last_n", "merchant", "summary"],
                    "description": "Type of filter to apply.",
                },
                "filter_value": {
                    "type": "string",
                    "description": (
                        "Filter value: MM/YYYY for month, category name for expense_type, "
                        "number for last_n, merchant name for merchant. "
                        "Not needed for 'all' or 'summary'."
                    ),
                },
            },
            "required": ["filter_type"],
        },
    },
    {
        "name": "delete_receipt",
        "description": (
            "Delete a receipt by its sequence number. The remaining receipts will be re-numbered. "
            "Use this when the user asks to remove or delete a specific receipt."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seq_number": {
                    "type": "integer",
                    "description": "The sequence number of the receipt to delete.",
                },
            },
            "required": ["seq_number"],
        },
    },
    {
        "name": "send_whatsapp",
        "description": (
            "Send a WhatsApp message to the user. Use this as the final action to confirm "
            "what was done or to respond to a query. Always call this to reply to the user."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Recipient phone number (without whatsapp: prefix).",
                },
                "message": {
                    "type": "string",
                    "description": "The message text to send.",
                },
            },
            "required": ["to", "message"],
        },
    },
]


async def execute_tool(name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool by name with the given input. Returns a JSON-serializable result."""
    logger.info("Executing tool: %s with input: %s", name, json.dumps(input_data, default=str)[:200])

    if name == "extract_receipt":
        receipt = await extract_receipt(input_data["image_path"])
        return {"success": True, **receipt.to_dict()}

    if name == "check_duplicate":
        dup = is_duplicate(
            ReceiptData(
                date=input_data["date"],
                merchant=input_data["merchant"],
                amount=input_data["amount"],
                currency="",
                expense_type="",
                description="",
            )
        )
        return {"is_duplicate": dup}

    if name == "log_receipt":
        data = ReceiptData(
            date=input_data["date"],
            amount=input_data["amount"],
            currency=input_data["currency"],
            expense_type=input_data["expense_type"],
            merchant=input_data["merchant"],
            description=input_data["description"],
        )
        seq = append_receipt(data, image_path=input_data.get("image_path", ""))
        return {"seq_number": seq}

    if name == "send_email":
        receipts_data = input_data.get("receipts")
        custom_to = input_data.get("to")
        custom_subject = input_data.get("subject")
        custom_body = input_data.get("body")

        if custom_subject and custom_body:
            # Custom report email — attach images from receipts if provided
            attachments = []
            if receipts_data:
                for r in receipts_data:
                    img = r.get("image_path", "")
                    if img:
                        attachments.append(img)
            await asyncio.to_thread(
                send_summary_email,
                custom_subject,
                custom_body,
                custom_to,
                attachments or None,
            )
            return {"sent": True}

        if receipts_data:
            # Standard reimbursement email
            tuples = []
            for r in receipts_data:
                rd = ReceiptData(
                    date=r["date"],
                    amount=r["amount"],
                    currency=r["currency"],
                    expense_type=r["expense_type"],
                    merchant=r["merchant"],
                    description=r["description"],
                )
                tuples.append((rd, r.get("image_path", ""), r.get("seq_number", 0)))
            await asyncio.to_thread(send_reimbursement_email, tuples)
            return {"sent": True}

        return {"error": "No receipts or subject/body provided"}

    if name == "query_expenses":
        filter_type = input_data["filter_type"]
        filter_value = input_data.get("filter_value")

        if filter_type == "summary":
            return get_summary()

        rows = query_receipts(filter_type, filter_value)
        total_by_currency: dict[str, float] = {}
        for r in rows:
            c = r["currency"]
            total_by_currency[c] = total_by_currency.get(c, 0.0) + float(r["amount"])

        return {
            "count": len(rows),
            "receipts": rows,
            "totals": {k: round(v, 2) for k, v in total_by_currency.items()},
        }

    if name == "delete_receipt":
        deleted = delete_receipt(input_data["seq_number"])
        return {"deleted": deleted}

    if name == "send_whatsapp":
        await send_text_message(input_data["to"], input_data["message"])
        return {"sent": True}

    return {"error": f"Unknown tool: {name}"}
