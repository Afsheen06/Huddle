"""Create a draft PayPal Sandbox invoice from the terminal.

This helper intentionally does not send invoices. Sending must go through the
Referee queue so a person can review and approve the action first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Running `python scripts/test_invoice.py` puts scripts/ on sys.path. Add the
# project root so the app package can be imported when using that exact command.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.paypal_client import create_invoice  # noqa: E402


def main() -> None:
    """Create one draft invoice and display its ID without sending it."""
    client_email = os.getenv("TEST_CLIENT_EMAIL", "").strip()
    if not client_email:
        raise SystemExit(
            "Set TEST_CLIENT_EMAIL in .env to the email of your PayPal Sandbox "
            "PERSONAL test account before running this script."
        )

    print("Creating a draft invoice in PayPal Sandbox...")
    invoice = create_invoice(
        client_name="Sandbox Test Customer",
        client_email=client_email,
        description="Freelance project test invoice",
        amount="25.00",
        currency="USD",
        due_in_days=7,
    )
    invoice_id = invoice.get("id")
    if not invoice_id:
        raise RuntimeError("PayPal created a response without an invoice ID.")
    print(f"Draft invoice ID: {invoice_id}")
    print(f"Status: {invoice.get('status') or 'DRAFT'}")
    print("This invoice is a draft and was not sent. Use Huddle's Referee queue to send it after review.")


if __name__ == "__main__":
    main()
