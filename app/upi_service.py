"""Build standard UPI payment links and player QR codes."""

from __future__ import annotations

import base64
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from urllib.parse import urlencode

import qrcode

from app import settings


def _decimal_amount(value: Any) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("UPI fee amount must be a valid positive number.") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("UPI fee amount must be a valid positive number.")
    return amount.quantize(Decimal("0.01"))


def build_upi_link(
    player_name: str,
    amount_inr: Any,
    note: str | None = None,
) -> str:
    """Create an encoded UPI intent link using the configured club identity."""
    amount = _decimal_amount(amount_inr)
    payment_note = (note or f"Monthly club fee - {player_name}").strip()[:80]
    query = urlencode(
        {
            "pa": settings.CLUB_UPI_ID,
            "pn": settings.CLUB_NAME,
            "am": format(amount, ".2f"),
            "cu": "INR",
            "tn": payment_note,
        }
    )
    return f"upi://pay?{query}"


def payment_details(player: dict[str, Any], *, include_qr: bool = False) -> dict[str, Any]:
    """Return rupee fee details and, when requested, a data-URL QR image."""
    amount = _decimal_amount(player.get("amount"))
    link = build_upi_link(str(player.get("player_name") or "Club player"), amount)
    result: dict[str, Any] = {
        "player_key": player.get("player_key"),
        "player_name": player.get("player_name"),
        "club_name": settings.CLUB_NAME,
        "upi_id": settings.CLUB_UPI_ID,
        "upi_is_placeholder": settings.UPI_ID_IS_PLACEHOLDER,
        "amount": {"currency_code": "INR", "value": format(amount, ".2f")},
        "upi_link": link,
    }
    if include_qr:
        image = qrcode.make(link)
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        result["qr_code_data_url"] = f"data:image/png;base64,{encoded}"
    return result
