"""Core agentic loop: Claude decides which tools to call based on user messages."""

import asyncio
import base64
import json
import logging
import mimetypes
from datetime import datetime, timezone
from typing import Any

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam, ToolResultBlockParam, ToolUseBlockParam

from config import config
from tools import TOOL_SCHEMAS, execute_tool

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 20

def _build_system_prompt() -> str:
    today = datetime.now(tz=timezone.utc).strftime("%d/%m/%Y")
    month_year = datetime.now(tz=timezone.utc).strftime("%m/%Y")
    return (
        "You are a WhatsApp receipt reimbursement assistant. "
        "Users send you receipt photos and text commands via WhatsApp. "
        "You process receipts, track expenses, and answer queries.\n\n"
        f"Today's date is {today}. The current month is {month_year}. "
        "Use this when interpreting relative dates like 'this month' or 'last week'.\n\n"
        "## Your capabilities (via tools):\n"
        "- extract_receipt: Extract data from receipt images using vision\n"
        "- check_duplicate: Check if a receipt is already logged\n"
        "- log_receipt: Save a receipt to the expense log\n"
        "- send_email: Send reimbursement emails with receipts attached\n"
        "- query_expenses: Look up spending history with filters\n"
        "- delete_receipt: Remove a receipt from the log\n"
        "- send_whatsapp: Send a message back to the user (ALWAYS do this as final action)\n\n"
        "## When processing receipt images:\n"
        "1. Use extract_receipt to get the data\n"
        "2. Use check_duplicate to verify it's not already logged\n"
        "3. If not a duplicate, use log_receipt to save it\n"
        "4. Use send_email to email the reimbursement\n"
        "5. Use send_whatsapp to confirm to the user\n\n"
        "## When handling queries:\n"
        "1. Use query_expenses with appropriate filters\n"
        "2. Use send_whatsapp to reply with the results\n\n"
        "## When handling deletions:\n"
        "1. Use delete_receipt with the sequence number\n"
        "2. Use send_whatsapp to confirm\n\n"
        "## Important rules:\n"
        "- NEVER invent, guess, or hallucinate values for tool inputs. "
        "Only use data that was returned by a previous tool call or provided by the user. "
        "If a field is unknown or unavailable, omit it or leave it empty.\n"
        "- ALWAYS end with send_whatsapp to reply to the user\n"
        "- Be concise in WhatsApp messages, use short lines and emojis sparingly\n"
        "- If an image is blurry or not a receipt, tell the user via send_whatsapp\n"
        "- If the user's request is unclear, ask for clarification via send_whatsapp\n"
        "- The user's phone number is provided, use it for send_whatsapp 'to' field\n"
        "- When multiple images are sent, process them all and send a single batched email\n"
        "- For queries, format results clearly with totals"
    )


async def run_agent(
    sender: str,
    text: str | None = None,
    image_paths: list[str] | None = None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run the agentic loop for a user message.

    Args:
        sender: Phone number of the sender (without whatsapp: prefix).
        text: Text message from the user, if any.
        image_paths: Local paths to downloaded images, if any.
        dry_run: If True, skip send_whatsapp and send_email (for local testing).

    Returns:
        List of tool call results for inspection/testing.
    """
    client = AsyncAnthropic(api_key=config.anthropic_api_key)

    # Build the initial user message content
    user_content: list[dict[str, Any]] = []

    # Add images as base64 so Claude can see them
    for img_path in image_paths or []:
        mime_type = mimetypes.guess_type(img_path)[0] or "image/jpeg"
        with open(img_path, "rb") as f:
            img_data = base64.standard_b64encode(f.read()).decode("utf-8")
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": mime_type, "data": img_data},
        })

    # Build text context
    context_parts = [f"Sender phone: {sender}"]
    if image_paths:
        for i, p in enumerate(image_paths):
            context_parts.append(f"Image {i + 1} path: {p}")
    if text:
        context_parts.append(f"User message: {text}")
    else:
        context_parts.append("User sent receipt image(s) with no text.")

    user_content.append({"type": "text", "text": "\n".join(context_parts)})

    messages: list[MessageParam] = [{"role": "user", "content": user_content}]  # type: ignore[list-item]

    tool_log: list[dict[str, Any]] = []

    for iteration in range(MAX_ITERATIONS):
        logger.info("Agent iteration %d", iteration + 1)

        response = await client.messages.create(
            model=config.agent_model,
            max_tokens=4096,
            system=_build_system_prompt(),
            tools=TOOL_SCHEMAS,  # type: ignore[arg-type]
            messages=messages,
        )

        logger.info("Stop reason: %s", response.stop_reason)

        if response.stop_reason == "end_turn":
            # Claude is done — extract any final text
            for block in response.content:
                if hasattr(block, "text"):
                    logger.info("Agent final text: %s", block.text)  # type: ignore[union-attr]
            break

        # Process tool use blocks
        tool_use_blocks: list[ToolUseBlockParam] = []
        assistant_content = []
        for block in response.content:
            if block.type == "tool_use":
                tool_use_blocks.append(block)  # type: ignore[arg-type]
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
            elif block.type == "text":
                assistant_content.append({"type": "text", "text": block.text})

        if not tool_use_blocks:
            break

        # Append assistant message
        messages.append({"role": "assistant", "content": assistant_content})

        # Execute all tool calls concurrently
        async def _exec_one(tool_block: Any) -> ToolResultBlockParam:
            name = tool_block.name if hasattr(tool_block, "name") else tool_block["name"]
            tool_input = tool_block.input if hasattr(tool_block, "input") else tool_block["input"]
            tool_id = tool_block.id if hasattr(tool_block, "id") else tool_block["id"]

            if dry_run and name in ("send_whatsapp", "send_email"):
                result = {"skipped": True, "reason": "dry_run mode"}
                logger.info("Dry-run skip: %s", name)
            else:
                try:
                    result = await execute_tool(name, tool_input)
                except Exception as e:
                    logger.exception("Tool %s failed", name)
                    result = {"error": str(e)}

            tool_log.append({"tool": name, "input": tool_input, "result": result})
            return {"type": "tool_result", "tool_use_id": tool_id, "content": json.dumps(result)}  # type: ignore[typeddict-item]

        tool_results = await asyncio.gather(*[_exec_one(tb) for tb in tool_use_blocks])

        # Append tool results
        messages.append({"role": "user", "content": list(tool_results)})

    else:
        logger.warning("Agent hit max iterations (%d)", MAX_ITERATIONS)

    return tool_log
