"""Small environment-backed settings shared across Huddle services."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# India is the app's fee currency. PayPal Sandbox invoices deliberately remain
# USD because INR is absent from PayPal's current supported currency table.
DEFAULT_CURRENCY = os.getenv("DEFAULT_CURRENCY", "INR").strip().upper() or "INR"
CURRENCY_SYMBOL = os.getenv("CURRENCY_SYMBOL", "₹").strip() or "₹"
PAYPAL_TEST_CURRENCY = "USD"

# These defaults are plainly fake and must be replaced for real UPI collections.
CLUB_UPI_ID = os.getenv("CLUB_UPI_ID", "yourclub@upi").strip() or "yourclub@upi"
CLUB_NAME = os.getenv("CLUB_NAME", "Your Club").strip() or "Your Club"
UPI_ID_IS_PLACEHOLDER = CLUB_UPI_ID.casefold() == "yourclub@upi"
