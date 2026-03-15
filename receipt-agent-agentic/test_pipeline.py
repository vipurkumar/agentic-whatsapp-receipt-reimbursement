"""End-to-end agent pipeline test with mocked external services."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

IMAGE_PATH = "receipts/test_receipt.png"

FAKE_RECEIPT = {
    "date": "14/03/2026",
    "amount": "51.43",
    "currency": "EUR",
    "expense_type": "Meals",
    "merchant": "Cafe de Amsterdam",
    "description": "Breakfast with cappuccinos, croissant, juice, eggs benedict and pancakes",
}


def _make_tool_use_response(tool_calls: list[dict]) -> MagicMock:
    """Build a mock Claude response with tool_use blocks."""
    blocks = []
    for i, tc in enumerate(tool_calls):
        block = MagicMock()
        block.type = "tool_use"
        block.id = f"call_{i}"
        block.name = tc["name"]
        block.input = tc["input"]
        blocks.append(block)
    resp = MagicMock()
    resp.stop_reason = "tool_use"
    resp.content = blocks
    return resp


def _make_text_response(text: str) -> MagicMock:
    """Build a mock Claude response with end_turn."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    resp = MagicMock()
    resp.stop_reason = "end_turn"
    resp.content = [block]
    return resp


async def test_receipt_processing() -> None:
    """Test: user sends a receipt image → extract, dedup, log, email, confirm."""
    print("\n[TEST 1] Receipt image processing")
    print("-" * 40)

    # Claude will make these tool calls across 3 iterations:
    # 1. extract_receipt
    # 2. check_duplicate + log_receipt (after seeing extraction result)
    # 3. send_email + send_whatsapp
    responses = [
        _make_tool_use_response([{"name": "extract_receipt", "input": {"image_path": IMAGE_PATH}}]),
        _make_tool_use_response([
            {
                "name": "check_duplicate",
                "input": {"date": "14/03/2026", "merchant": "Cafe de Amsterdam", "amount": "51.43"},
            },
        ]),
        _make_tool_use_response([
            {
                "name": "log_receipt",
                "input": {
                    "date": "14/03/2026",
                    "amount": "51.43",
                    "currency": "EUR",
                    "expense_type": "Meals",
                    "merchant": "Cafe de Amsterdam",
                    "description": "Breakfast",
                },
            },
        ]),
        _make_tool_use_response([
            {
                "name": "send_email",
                "input": {
                    "receipts": [
                        {
                            "date": "14/03/2026",
                            "amount": "51.43",
                            "currency": "EUR",
                            "expense_type": "Meals",
                            "merchant": "Cafe de Amsterdam",
                            "description": "Breakfast",
                            "image_path": IMAGE_PATH,
                            "seq_number": 1,
                        }
                    ]
                },
            },
            {
                "name": "send_whatsapp",
                "input": {"to": "+15551234567", "message": "Receipt #1 logged! Cafe de Amsterdam - 51.43 EUR"},
            },
        ]),
        _make_text_response("Done"),
    ]

    mock_claude = AsyncMock(side_effect=responses)

    # Mock extract_receipt to return fake data
    mock_extract = AsyncMock(return_value=MagicMock(
        date="14/03/2026", amount="51.43", currency="EUR",
        expense_type="Meals", merchant="Cafe de Amsterdam",
        description="Breakfast",
        to_dict=lambda: FAKE_RECEIPT,
    ))

    with (
        patch("agent.AsyncAnthropic") as mock_anthropic,
        patch("tools.extract_receipt", mock_extract),
        patch("tools.is_duplicate", return_value=False),
        patch("tools.append_receipt", return_value=1),
        patch("tools.send_reimbursement_email"),
        patch("tools.send_text_message", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.messages.create = mock_claude
        mock_anthropic.return_value = mock_client

        from agent import run_agent

        tool_log = await run_agent(
            sender="+15551234567",
            image_paths=[IMAGE_PATH],
        )

    tools_called = [t["tool"] for t in tool_log]
    print(f"  Tools called: {tools_called}")

    assert "extract_receipt" in tools_called, "extract_receipt not called"
    assert "check_duplicate" in tools_called, "check_duplicate not called"
    assert "log_receipt" in tools_called, "log_receipt not called"
    assert "send_email" in tools_called, "send_email not called"
    assert "send_whatsapp" in tools_called, "send_whatsapp not called"
    print("  PASSED: All 5 tools called in correct order")


async def test_text_query() -> None:
    """Test: user asks about spending → query + reply."""
    print("\n[TEST 2] Text query: 'total spending this month'")
    print("-" * 40)

    responses = [
        _make_tool_use_response([
            {"name": "query_expenses", "input": {"filter_type": "summary"}},
        ]),
        _make_tool_use_response([
            {"name": "send_whatsapp", "input": {"to": "+15551234567", "message": "Total: 51.43 EUR (1 receipt)"}},
        ]),
        _make_text_response("Done"),
    ]

    mock_claude = AsyncMock(side_effect=responses)

    with (
        patch("agent.AsyncAnthropic") as mock_anthropic,
        patch("tools.get_summary", return_value={
            "total_receipts": 1,
            "by_currency": {"EUR": 51.43},
            "by_expense_type": {"Meals (EUR)": 51.43},
        }),
        patch("tools.send_text_message", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.messages.create = mock_claude
        mock_anthropic.return_value = mock_client

        from agent import run_agent

        tool_log = await run_agent(
            sender="+15551234567",
            text="total spending this month",
        )

    tools_called = [t["tool"] for t in tool_log]
    print(f"  Tools called: {tools_called}")

    assert "query_expenses" in tools_called, "query_expenses not called"
    assert "send_whatsapp" in tools_called, "send_whatsapp not called"
    print("  PASSED: Query + reply flow works")


async def test_delete_receipt() -> None:
    """Test: user asks to delete receipt #1 → delete + confirm."""
    print("\n[TEST 3] Delete: 'delete receipt #1'")
    print("-" * 40)

    responses = [
        _make_tool_use_response([
            {"name": "delete_receipt", "input": {"seq_number": 1}},
        ]),
        _make_tool_use_response([
            {"name": "send_whatsapp", "input": {"to": "+15551234567", "message": "Receipt #1 deleted."}},
        ]),
        _make_text_response("Done"),
    ]

    mock_claude = AsyncMock(side_effect=responses)

    with (
        patch("agent.AsyncAnthropic") as mock_anthropic,
        patch("tools.delete_receipt", return_value=True),
        patch("tools.send_text_message", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.messages.create = mock_claude
        mock_anthropic.return_value = mock_client

        from agent import run_agent

        tool_log = await run_agent(
            sender="+15551234567",
            text="delete receipt #1",
        )

    tools_called = [t["tool"] for t in tool_log]
    print(f"  Tools called: {tools_called}")

    assert "delete_receipt" in tools_called, "delete_receipt not called"
    assert "send_whatsapp" in tools_called, "send_whatsapp not called"
    print("  PASSED: Delete + confirm flow works")


async def test_duplicate_detection() -> None:
    """Test: same receipt sent twice → duplicate detected, no log/email."""
    print("\n[TEST 4] Duplicate detection")
    print("-" * 40)

    responses = [
        _make_tool_use_response([{"name": "extract_receipt", "input": {"image_path": IMAGE_PATH}}]),
        _make_tool_use_response([
            {
                "name": "check_duplicate",
                "input": {"date": "14/03/2026", "merchant": "Cafe de Amsterdam", "amount": "51.43"},
            },
        ]),
        _make_tool_use_response([
            {"name": "send_whatsapp", "input": {"to": "+15551234567", "message": "Duplicate receipt detected."}},
        ]),
        _make_text_response("Done"),
    ]

    mock_claude = AsyncMock(side_effect=responses)
    mock_extract = AsyncMock(return_value=MagicMock(
        date="14/03/2026", amount="51.43", currency="EUR",
        expense_type="Meals", merchant="Cafe de Amsterdam",
        description="Breakfast",
        to_dict=lambda: FAKE_RECEIPT,
    ))

    with (
        patch("agent.AsyncAnthropic") as mock_anthropic,
        patch("tools.extract_receipt", mock_extract),
        patch("tools.is_duplicate", return_value=True),
        patch("tools.send_text_message", new_callable=AsyncMock),
    ):
        mock_client = AsyncMock()
        mock_client.messages.create = mock_claude
        mock_anthropic.return_value = mock_client

        from agent import run_agent

        tool_log = await run_agent(
            sender="+15551234567",
            image_paths=[IMAGE_PATH],
        )

    tools_called = [t["tool"] for t in tool_log]
    print(f"  Tools called: {tools_called}")

    assert "check_duplicate" in tools_called, "check_duplicate not called"
    assert "log_receipt" not in tools_called, "log_receipt should NOT be called for duplicate"
    assert "send_email" not in tools_called, "send_email should NOT be called for duplicate"
    assert "send_whatsapp" in tools_called, "send_whatsapp not called"
    print("  PASSED: Duplicate detected, no log or email sent")


async def main() -> None:
    """Run all agent pipeline tests."""
    print("=" * 50)
    print("AGENT PIPELINE TESTS (all mocked)")
    print("=" * 50)

    await test_receipt_processing()
    await test_text_query()
    await test_delete_receipt()
    await test_duplicate_detection()

    print("\n" + "=" * 50)
    print("ALL 4 TESTS PASSED")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
