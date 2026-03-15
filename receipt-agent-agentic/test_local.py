"""Local test script for the agentic receipt processor."""

import argparse
import asyncio
import json
import logging

from agent import run_agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test the agentic receipt processor locally.")
    parser.add_argument("--image", action="append", help="Path to a receipt image (can be repeated).")
    parser.add_argument("--text", type=str, help="Text message to send to the agent.")
    parser.add_argument("--sender", type=str, default="+15551234567", help="Simulated sender phone number.")
    args = parser.parse_args()

    if not args.image and not args.text:
        parser.error("Provide at least --image or --text")

    print(f"Sender: {args.sender}")
    if args.text:
        print(f"Text: {args.text}")
    if args.image:
        print(f"Images: {args.image}")
    print()

    tool_log = await run_agent(
        sender=args.sender,
        text=args.text,
        image_paths=args.image,
        dry_run=True,
    )

    print("\n=== Tool Call Log ===")
    for i, entry in enumerate(tool_log, 1):
        print(f"\n--- Tool Call {i}: {entry['tool']} ---")
        print(f"Input: {json.dumps(entry['input'], indent=2, default=str)}")
        print(f"Result: {json.dumps(entry['result'], indent=2, default=str)}")

    print(f"\nTotal tool calls: {len(tool_log)}")


if __name__ == "__main__":
    asyncio.run(main())
