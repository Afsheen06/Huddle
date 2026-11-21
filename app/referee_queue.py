"""Human-review queue for PayPal actions that can notify parents or cancel bills."""

from __future__ import annotations

import threading
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app import paypal_client
from app.roster_service import get_roster, player_key
from app.storage import read_json, write_json
from app.settings import CURRENCY_SYMBOL


_QUEUE_LOCK = threading.RLock()
_UNPAID_STATUSES = {"SENT", "UNPAID", "PARTIALLY_PAID", "PAYMENT_PENDING", "SHARED"}
_DRAFT_STATUSES = {"DRAFT"}


def _queue_file() -> list[dict[str, Any]]:
    data = read_json("queue.json", [])
    if not isinstance(data, list):
        raise RuntimeError("data/queue.json must contain a JSON list.")
    return data


def get_queue() -> list[dict[str, Any]]:
    """Return all queue records, newest first."""
    with _QUEUE_LOCK:
        return sorted(_queue_file(), key=lambda item: item.get("created_at", ""), reverse=True)


def clear_queue() -> None:
    """Clear local Referee proposals as part of an intentional demo reset."""
    with _QUEUE_LOCK:
        write_json("queue.json", [])


def _brief(invoice: dict[str, Any]) -> dict[str, Any]:
    detail = invoice.get("detail") or {}
    billing = {}
    recipients = invoice.get("primary_recipients") or []
    if recipients:
        billing = recipients[0].get("billing_info") or {}
    amount = invoice.get("due_amount") or invoice.get("amount") or {}
    name = billing.get("name") or {}
    linked = (read_json("invoice_map.json", {}) or {}).get(str(invoice.get("id") or ""), {})
    return {
        "id": invoice.get("id"),
        "invoice_number": detail.get("invoice_number"),
        "status": str(invoice.get("status") or "").upper(),
        "amount": amount.get("value"),
        "currency": amount.get("currency_code"),
        "recipient_name": name.get("full_name") or name.get("given_name"),
        "recipient_email": billing.get("email_address"),
        "fee_amount_inr": linked.get("fee_amount_inr"),
        "upi_link": linked.get("upi_link"),
    }


def _validate_target(action_type: str, invoice_id: str) -> dict[str, Any]:
    """Fetch the invoice and ensure the proposed operation fits its current state."""
    invoice = paypal_client.get_invoice(invoice_id)
    status = str(invoice.get("status") or "").upper()
    if action_type in {"send_invoice", "bulk_send"} and status not in _DRAFT_STATUSES:
        raise ValueError(f"Invoice {invoice_id} is {status}, not a draft, so it cannot be sent.")
    if action_type in {"send_reminder", "cancel_invoice"} and status not in _UNPAID_STATUSES:
        raise ValueError(
            f"Invoice {invoice_id} is {status}; reminders and cancellation require a sent, unpaid invoice."
        )
    return invoice


def _summary(action_type: str, briefs: list[dict[str, Any]], reminder_message: str | None) -> str:
    if action_type == "bulk_send":
        total = sum((Decimal(str(item.get("amount") or "0")) for item in briefs), Decimal("0"))
        currencies = {item.get("currency") for item in briefs if item.get("currency")}
        currency = next(iter(currencies)) if len(currencies) == 1 else "mixed currencies"
        rupees = sum(
            Decimal(str(_fee_value(item.get("fee_amount_inr")) or 0))
            for item in briefs
        )
        return f"Send {len(briefs)} PayPal Sandbox test invoices (USD test total {total:.2f} {currency}; club fees total {CURRENCY_SYMBOL}{rupees:.2f} INR)."
    item = briefs[0]
    label = item.get("invoice_number") or item["id"]
    recipient = item.get("recipient_name") or item.get("recipient_email") or "the listed customer"
    if action_type == "send_invoice":
        fee = _fee_value(item.get("fee_amount_inr"))
        fee_label = f"; linked club fee {CURRENCY_SYMBOL}{fee} INR" if fee is not None else "; no INR roster fee is linked"
        return f"Send invoice {label} (PayPal Sandbox test amount {item.get('amount')} {item.get('currency')}{fee_label}) to {recipient}."
    if action_type == "cancel_invoice":
        return f"Cancel sent invoice {label} for {recipient}; PayPal may notify the customer."
    note_preview = (reminder_message or "").replace("\n", " ").strip()
    return f"Email {recipient} a reminder for invoice {label}: {note_preview}"


def _fee_value(value: Any) -> Any:
    """Read INR fees from either current numeric or earlier object records."""
    return value.get("value") if isinstance(value, dict) else value


def propose_action(
    action_type: str,
    invoice_ids: list[str],
    reminder_message: str | None = None,
) -> dict[str, Any]:
    """Save a verified action for a person to review; never calls send/remind/cancel."""
    allowed = {"send_invoice", "bulk_send", "send_reminder", "cancel_invoice"}
    if action_type not in allowed:
        raise ValueError(f"Unsupported proposed action: {action_type}")
    ids = list(dict.fromkeys(str(item).strip() for item in invoice_ids if str(item).strip()))
    if not ids:
        raise ValueError("At least one real invoice ID is required.")
    if action_type == "bulk_send" and len(ids) < 2:
        raise ValueError("bulk_send needs at least two draft invoice IDs; use send_invoice for one.")
    if action_type != "bulk_send" and len(ids) != 1:
        raise ValueError(f"{action_type} expects exactly one invoice ID.")
    if action_type == "send_reminder" and not (reminder_message or "").strip():
        raise ValueError("A reminder message is required before it can be proposed.")

    # Resolve every ID with PayPal before saving a proposal so invented IDs
    # cannot enter the queue and a human sees the real status and recipient.
    invoices = [_validate_target(action_type, invoice_id) for invoice_id in ids]
    briefs = [_brief(invoice) for invoice in invoices]
    record: dict[str, Any] = {
        "id": f"Q-{uuid.uuid4().hex[:12].upper()}",
        "action_type": action_type,
        "target_invoice_ids": ids,
        "summary": _summary(action_type, briefs, reminder_message),
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "targets": briefs,
    }
    if action_type == "send_reminder":
        record["reminder_message"] = reminder_message.strip()[:4000]

    with _QUEUE_LOCK:
        queue = _queue_file()
        queue.append(record)
        write_json("queue.json", queue)
    return record


def _execute_approved(record: dict[str, Any]) -> list[dict[str, Any]]:
    action_type = record["action_type"]
    invoice_ids = record["target_invoice_ids"]
    results: list[dict[str, Any]] = []
    # Validate every invoice before the first email/cancel request. This avoids
    # avoidable partial bulk sends when a later invoice is already paid or was
    # otherwise changed while the queue item waited for approval.
    for invoice_id in invoice_ids:
        _validate_target(action_type, invoice_id)

    for invoice_id in invoice_ids:
        if action_type in {"send_invoice", "bulk_send"}:
            result = paypal_client.send_invoice(invoice_id)
        elif action_type == "send_reminder":
            result = paypal_client.send_reminder(invoice_id, note=record["reminder_message"])
        elif action_type == "cancel_invoice":
            result = paypal_client.cancel_invoice(invoice_id)
        else:
            # Never interpret an unknown/corrupt queue action as a cancellation.
            raise ValueError(f"Unsupported queued action type: {action_type}")
        results.append({"invoice_id": invoice_id, "result": result or {"success": True}})
    return results


def approve_action(queue_id: str) -> dict[str, Any]:
    """Execute a pending proposal after a human calls the approval endpoint."""
    with _QUEUE_LOCK:
        queue = _queue_file()
        record = next((item for item in queue if item.get("id") == queue_id), None)
        if not record:
            raise KeyError(f"Queue item {queue_id} was not found.")
        if record.get("status") != "pending":
            raise ValueError(f"Queue item {queue_id} is {record.get('status')}, not pending.")
        record["status"] = "executing"
        record["approved_at"] = datetime.now(timezone.utc).isoformat()
        write_json("queue.json", queue)

    try:
        results = _execute_approved(record)
        state = "approved"
        error = None
    except Exception as exc:
        results = []
        state = "failed"
        error = str(exc)

    with _QUEUE_LOCK:
        queue = _queue_file()
        current = next(item for item in queue if item.get("id") == queue_id)
        current["status"] = state
        current["result"] = results
        if error:
            current["error"] = error
        write_json("queue.json", queue)
        return current


def reject_action(queue_id: str, reason: str | None = None) -> dict[str, Any]:
    """Mark a pending proposal rejected without calling PayPal."""
    with _QUEUE_LOCK:
        queue = _queue_file()
        record = next((item for item in queue if item.get("id") == queue_id), None)
        if not record:
            raise KeyError(f"Queue item {queue_id} was not found.")
        if record.get("status") != "pending":
            raise ValueError(f"Queue item {queue_id} is {record.get('status')}, not pending.")
        record["status"] = "rejected"
        record["rejected_at"] = datetime.now(timezone.utc).isoformat()
        if reason:
            record["rejection_reason"] = reason[:500]
        write_json("queue.json", queue)
        return record


def approve_all() -> dict[str, Any]:
    """Approve each item that was pending when this endpoint was called."""
    with _QUEUE_LOCK:
        ids = [item["id"] for item in _queue_file() if item.get("status") == "pending"]
    results = [approve_action(queue_id) for queue_id in ids]
    return {"approved_count": sum(item.get("status") == "approved" for item in results), "items": results}


def _reminder_text(parent_name: str | None, days_overdue: int, label: str, amount: str, upi_link: str) -> str:
    greeting = parent_name.strip() if parent_name else "there"
    if days_overdue < 3:
        message = f"Hi {greeting}, just a friendly reminder that the club fee for invoice {label} is {CURRENCY_SYMBOL}{amount} INR and is still outstanding. Whenever convenient, please pay using the UPI link below. Thank you!"
    elif days_overdue <= 10:
        message = f"Hello {greeting}, our records show the club fee for invoice {label} ({CURRENCY_SYMBOL}{amount} INR) is {days_overdue} days overdue. Could you please arrange payment using the UPI link below, or let us know if you have questions? Thank you."
    else:
        message = f"Dear {greeting}, the club fee for invoice {label} ({CURRENCY_SYMBOL}{amount} INR) remains unpaid and is {days_overdue} days overdue. Please arrange payment using the UPI link below at your earliest convenience, or contact us if there is an issue. Thank you."
    return f"{message}\nUPI payment link: {upi_link}"


def chase_overdue() -> dict[str, Any]:
    """Draft tone-aware reminders for unpaid invoices into the review queue."""
    invoice_data = paypal_client.list_invoices()
    invoice_map = read_json("invoice_map.json", {})
    roster = get_roster()
    today = date.today()
    queued: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []

    for invoice in invoice_data.get("items") or []:
        status = str(invoice.get("status") or "").upper()
        if status not in _UNPAID_STATUSES:
            continue
        balance = invoice.get("due_amount") or invoice.get("effective_due_amount") or invoice.get("amount") or {}
        try:
            amount_value = Decimal(str(balance.get("value", "0")))
        except (InvalidOperation, ValueError):
            continue
        if amount_value <= 0:
            continue

        invoice_id = str(invoice.get("id") or "")
        linked = invoice_map.get(invoice_id) or {}
        # Only propose parent-facing reminders for invoices linked to a known
        # INR roster fee and payment link. Never treat USD Sandbox as rupees.
        fee_amount = linked.get("fee_amount_inr")
        fee_value = fee_amount.get("value") if isinstance(fee_amount, dict) else fee_amount
        upi_link = linked.get("upi_link")
        if not fee_value or not upi_link:
            skipped.append({"invoice_id": invoice_id, "reason": "No linked INR roster fee and UPI link; no reminder was drafted."})
            continue
        parent_name = linked.get("parent_name")
        if not parent_name:
            recipients = invoice.get("primary_recipients") or []
            billing = (recipients[0].get("billing_info") or {}) if recipients else {}
            parent_name = (billing.get("name") or {}).get("full_name") or (billing.get("name") or {}).get("given_name")
            if not parent_name:
                email = str(billing.get("email_address") or "").casefold()
                matches = [p for p in roster if (p.get("parent_email") or "").casefold() == email]
                if len(matches) == 1:
                    parent_name = matches[0].get("parent_name")

        details = invoice.get("detail") or {}
        payment_term = details.get("payment_term") or {}
        raw_due = payment_term.get("due_date") or invoice.get("due_date")
        try:
            due = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00")).date() if raw_due else None
        except ValueError:
            due = None
        days_overdue = max(0, (today - due).days) if due else 0
        number = details.get("invoice_number") or invoice_id
        note = _reminder_text(parent_name, days_overdue, str(number), str(fee_value), upi_link)
        try:
            queued.append(propose_action("send_reminder", [invoice_id], reminder_message=note))
        except Exception as exc:
            skipped.append({"invoice_id": invoice_id, "reason": str(exc)})

    return {
        "queued_count": len(queued),
        "queue_items": queued,
        "skipped": skipped,
        "note": "Reminders are drafts for human review; none were sent.",
    }
