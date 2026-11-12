"""Small PayPal Sandbox client used by the first, non-AI project step."""

from __future__ import annotations

import os
import threading
import time
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import requests
from dotenv import load_dotenv

# Load settings from the project-root .env file, regardless of the caller's
# current working directory. Existing process environment variables take
# precedence, which is useful in deployment environments.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

_TIMEOUT_SECONDS = 30
_token_lock = threading.Lock()
_cached_token: str | None = None
_token_expires_at = 0.0


def _setting(name: str) -> str:
    """Return a required setting without ever including its value in errors."""
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing required setting {name}. Add it to the project-root .env file."
        )
    return value


def _base_url() -> str:
    """Read and normalize the PayPal API base URL."""
    return _setting("PAYPAL_BASE_URL").rstrip("/")


def _paypal_error(response: requests.Response) -> str:
    """Extract PayPal's human-readable error from a failed HTTP response."""
    try:
        data = response.json()
    except ValueError:
        body = response.text.strip()
        return body or f"HTTP {response.status_code} (no response body)"

    # PayPal commonly sends {"name": ..., "message": ..., "details": ...}.
    message = data.get("message") or data.get("error_description")
    name = data.get("name") or data.get("error")
    details = data.get("details")
    parts = [str(part) for part in (name, message) if part]
    if isinstance(details, list):
        for detail in details:
            if isinstance(detail, dict):
                description = detail.get("description") or detail.get("issue")
                if description:
                    parts.append(str(description))
    elif details:
        parts.append(str(details))
    return ": ".join(parts) if parts else str(data)


def _raise_for_paypal_error(response: requests.Response, action: str) -> None:
    """Raise a readable exception for any unsuccessful PayPal response."""
    if not response.ok:
        raise RuntimeError(
            f"PayPal {action} failed (HTTP {response.status_code}): "
            f"{_paypal_error(response)}"
        )


def get_access_token() -> str:
    """Get a cached OAuth token, refreshing it shortly before it expires."""
    global _cached_token, _token_expires_at

    # The lock prevents simultaneous requests from refreshing the same token.
    with _token_lock:
        if _cached_token and time.monotonic() < _token_expires_at:
            return _cached_token

        url = f"{_base_url()}/v1/oauth2/token"
        try:
            response = requests.post(
                url,
                auth=(_setting("PAYPAL_CLIENT_ID"), _setting("PAYPAL_SECRET")),
                headers={"Accept": "application/json", "Accept-Language": "en_US"},
                data={"grant_type": "client_credentials"},
                timeout=_TIMEOUT_SECONDS,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"Could not reach PayPal to get an access token: {exc}") from exc

        _raise_for_paypal_error(response, "access-token request")
        try:
            data = response.json()
            token = data["access_token"]
            expires_in = int(data.get("expires_in", 0))
        except (ValueError, KeyError, TypeError) as exc:
            raise RuntimeError("PayPal returned an invalid access-token response.") from exc

        if not token or expires_in <= 0:
            raise RuntimeError("PayPal returned an empty token or invalid expiration time.")

        _cached_token = str(token)
        # Refresh one minute early (or halfway through very short tokens).
        safety_margin = min(60, max(1, expires_in // 2))
        _token_expires_at = time.monotonic() + max(1, expires_in - safety_margin)
        return _cached_token


def _request(method: str, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
    """Send one authenticated request and return PayPal's JSON response."""
    url = f"{_base_url()}{path}"
    headers = {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    try:
        response = requests.request(
            method, url, headers=headers, json=json, timeout=_TIMEOUT_SECONDS
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach PayPal for {method} {path}: {exc}") from exc

    _raise_for_paypal_error(response, f"{method} {path}")
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"PayPal returned an invalid JSON response for {path}.") from exc


def create_invoice(
    client_name: str,
    client_email: str,
    description: str,
    amount: str | float | Decimal,
    currency: str = "USD",
    due_in_days: int = 7,
) -> dict[str, Any]:
    """Create a draft invoice with one item and return PayPal's invoice data."""
    if not client_name.strip():
        raise ValueError("client_name must not be empty.")
    if not client_email.strip():
        raise ValueError("client_email must not be empty.")
    if not description.strip():
        raise ValueError("description must not be empty.")
    if isinstance(due_in_days, bool) or not isinstance(due_in_days, int) or due_in_days < 0:
        raise ValueError("due_in_days must be a non-negative whole number.")
    try:
        decimal_amount = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a valid positive number.") from exc
    if not decimal_amount.is_finite() or decimal_amount <= 0:
        raise ValueError("amount must be a valid positive number.")

    normalized_currency = currency.strip().upper()
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise ValueError("currency must be a three-letter currency code, such as USD.")

    # PayPal assigns the invoice number separately before the draft is created.
    number_result = _request(
        "POST", "/v2/invoicing/generate-next-invoice-number", json={}
    )
    invoice_number = number_result.get("invoice_number")
    if not invoice_number:
        raise RuntimeError("PayPal did not return an invoice number.")

    due_date = (date.today() + timedelta(days=due_in_days)).isoformat()
    payload = {
        "detail": {
            "invoice_number": invoice_number,
            "currency_code": normalized_currency,
            # PayPal's supported term for a specific date is
            # DUE_ON_DATE_SPECIFIED (there is no CUSTOM enum value).
            "payment_term": {
                "term_type": "DUE_ON_DATE_SPECIFIED",
                "due_date": due_date,
            },
        },
        "primary_recipients": [
            {
                "billing_info": {
                    "name": {"given_name": client_name.strip()},
                    "email_address": client_email.strip(),
                }
            }
        ],
        "items": [
            {
                "name": description.strip(),
                "description": description.strip(),
                "quantity": "1",
                "unit_amount": {
                    "currency_code": normalized_currency,
                    "value": format(decimal_amount, ".2f"),
                },
            }
        ],
    }
    return _request("POST", "/v2/invoicing/invoices", json=payload)


def send_invoice(invoice_id: str) -> dict[str, Any]:
    """Send a previously created invoice to its recipient."""
    if not invoice_id.strip():
        raise ValueError("invoice_id must not be empty.")
    safe_invoice_id = quote(invoice_id.strip(), safe="")
    return _request(
        "POST",
        f"/v2/invoicing/invoices/{safe_invoice_id}/send",
        json={"send_to_recipient": True},
    )


def get_invoice(invoice_id: str) -> dict[str, Any]:
    """Fetch one invoice by its PayPal invoice ID."""
    if not invoice_id.strip():
        raise ValueError("invoice_id must not be empty.")
    safe_invoice_id = quote(invoice_id.strip(), safe="")
    return _request("GET", f"/v2/invoicing/invoices/{safe_invoice_id}")


def send_reminder(invoice_id: str, note: str | None = None) -> dict[str, Any]:
    """Ask PayPal to email the invoice recipient a payment reminder."""
    if not invoice_id.strip():
        raise ValueError("invoice_id must not be empty.")
    safe_invoice_id = quote(invoice_id.strip(), safe="")
    # PayPal may return HTTP 204 with no JSON body for this operation.
    reminder = {"send_to_recipient": True, "send_to_invoicer": True}
    if note:
        reminder["note"] = note[:4000]
    return _request(
        "POST",
        f"/v2/invoicing/invoices/{safe_invoice_id}/remind",
        json=reminder,
    )


def cancel_invoice(invoice_id: str) -> dict[str, Any]:
    """Cancel a sent invoice and ask PayPal to notify both parties."""
    if not invoice_id.strip():
        raise ValueError("invoice_id must not be empty.")
    safe_invoice_id = quote(invoice_id.strip(), safe="")
    return _request(
        "POST",
        f"/v2/invoicing/invoices/{safe_invoice_id}/cancel",
        json={"send_to_recipient": True, "send_to_invoicer": True},
    )


def list_invoices() -> dict[str, Any]:
    """Return all invoice pages (PayPal allows up to 100 entries per page)."""
    first_page = _request(
        "GET", "/v2/invoicing/invoices?page=1&page_size=100&total_required=true"
    )
    items = list(first_page.get("items") or [])
    total_pages = int(first_page.get("total_pages") or 1)

    # Fetch remaining pages so summaries do not silently omit older invoices.
    for page in range(2, total_pages + 1):
        page_result = _request(
            "GET",
            f"/v2/invoicing/invoices?page={page}&page_size=100&total_required=true",
        )
        items.extend(page_result.get("items") or [])

    first_page["items"] = items
    first_page["total_items"] = len(items)
    first_page["total_pages"] = total_pages
    return first_page


def get_summary() -> dict[str, Any]:
    """Summarize paid, unpaid, overdue, and outstanding invoice amounts.

    Overdue is a subset of unpaid. Draft invoices are not counted as unpaid
    because they have not been sent to a customer yet. Amounts are grouped by
    currency so values in different currencies are never added together.
    """
    invoice_data = list_invoices()
    today = date.today()
    paid_statuses = {"PAID", "PAID_EXTERNAL", "MARKED_AS_PAID"}
    closed_statuses = {
        "CANCELLED", "REFUNDED", "PARTIALLY_REFUNDED", "MARKED_AS_REFUNDED",
        "REFUNDED_EXTERNAL", "AUTO_CANCELLED", "DRAFT",
    }

    paid_count = 0
    unpaid_count = 0
    overdue_count = 0
    outstanding_by_currency: dict[str, Decimal] = {}

    for invoice in invoice_data.get("items") or []:
        status = str(invoice.get("status") or "").upper()
        if status in paid_statuses:
            paid_count += 1
            continue
        if status in closed_statuses:
            continue

        # PayPal's due_amount is the remaining balance after any payments.
        balance = invoice.get("due_amount") or invoice.get("effective_due_amount")
        if not balance:
            # Older/sandbox responses may omit due_amount. For an unpaid
            # invoice, its full amount is the best available fallback.
            balance = invoice.get("amount") or {}
        try:
            amount_value = Decimal(str(balance.get("value", "0")))
        except (InvalidOperation, ValueError):
            continue
        if not amount_value.is_finite() or amount_value <= 0:
            continue

        unpaid_count += 1
        currency_code = str(
            balance.get("currency_code")
            or (invoice.get("amount") or {}).get("currency_code")
            or "USD"
        ).upper()
        outstanding_by_currency[currency_code] = (
            outstanding_by_currency.get(currency_code, Decimal("0")) + amount_value
        )

        details = invoice.get("detail") or {}
        payment_term = details.get("payment_term") or {}
        raw_due_date = payment_term.get("due_date") or invoice.get("due_date")
        if raw_due_date:
            try:
                due_date = datetime.fromisoformat(
                    str(raw_due_date).replace("Z", "+00:00")
                ).date()
                if due_date < today:
                    overdue_count += 1
            except ValueError:
                # Ignore malformed dates in third-party data rather than
                # failing the entire account summary.
                pass

    formatted_totals = {
        currency: format(value, ".2f")
        for currency, value in sorted(outstanding_by_currency.items())
    }
    one_currency = next(iter(formatted_totals)) if len(formatted_totals) == 1 else None
    return {
        "paid_invoices": paid_count,
        "unpaid_invoices": unpaid_count,
        "overdue_invoices": overdue_count,
        "currency_code": one_currency,
        "total_amount_outstanding": (
            formatted_totals[one_currency] if one_currency else None
        ),
        "outstanding_by_currency": formatted_totals,
        "note": "Overdue invoices are included in the unpaid invoice count.",
    }
