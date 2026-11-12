"""Huddle's Gemini tool-calling agent. Sensitive PayPal actions are proposals only."""

from __future__ import annotations

import json
from typing import Any, Callable

from google.genai import types

from app import paypal_client, referee_queue, roster_service
from app.gemini_client import get_gemini_client

SYSTEM_INSTRUCTION = """You are Huddle, the AI treasurer for sports clubs. Help club volunteers manage invoices warmly and respectfully, especially when writing to parents. Default currency is USD. Never invent invoice IDs, customer emails, names, amounts, or other facts. If required details such as client email or amount are missing, ask the user. Creating invoices creates DRAFTS only. Never send, remind, or cancel directly: use propose_action to add the requested action to the Referee queue, where a human must approve it. Bulk billing also creates drafts only. Be clear that queue proposals have not been executed."""

# Explicit schemas help Gemini choose a tool and provide correctly named fields.
TOOLS = [
    {"name": "create_invoice", "description": "Create one DRAFT PayPal invoice. It is never sent automatically.", "parameters": {"type": "OBJECT", "properties": {"client_name": {"type": "STRING", "description": "Customer or parent name."}, "client_email": {"type": "STRING", "description": "Exact recipient email provided by the user; ask if missing."}, "description": {"type": "STRING", "description": "What the club is billing for."}, "amount": {"type": "NUMBER", "description": "Invoice amount."}, "currency": {"type": "STRING", "description": "ISO currency code; default USD."}, "due_in_days": {"type": "INTEGER", "description": "Days until due; default 7."}}, "required": ["client_name", "client_email", "description", "amount"]}},
    {"name": "bulk_create_invoices", "description": "Create DRAFT invoices for roster parents, optionally limited to an exact group/batch. Skips players without an email; never sends.", "parameters": {"type": "OBJECT", "properties": {"description": {"type": "STRING", "description": "What the club is billing for."}, "amount": {"type": "NUMBER", "description": "Amount per player."}, "due_in_days": {"type": "INTEGER", "description": "Days until due; default 7."}, "player_filter": {"type": "STRING", "description": "Optional exact group or batch name."}}, "required": ["description", "amount"]}},
    {"name": "list_invoices", "description": "List PayPal invoices and their actual IDs/statuses.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "get_summary", "description": "Get paid, unpaid, overdue and outstanding totals from PayPal.", "parameters": {"type": "OBJECT", "properties": {}}},
    {"name": "propose_action", "description": "Put a sensitive action into the human Referee queue. This does not execute it. Use for sending one draft, sending multiple drafts, reminding one sent unpaid invoice with a respectful message, or cancelling one sent unpaid invoice.", "parameters": {"type": "OBJECT", "properties": {"action_type": {"type": "STRING", "enum": ["send_invoice", "bulk_send", "send_reminder", "cancel_invoice"], "description": "Sensitive operation to propose."}, "invoice_ids": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Real invoice IDs returned by PayPal; one ID except bulk_send."}, "reminder_message": {"type": "STRING", "description": "Required warm reminder message for send_reminder."}}, "required": ["action_type", "invoice_ids"]}},
    {"name": "chase_overdue", "description": "Find unpaid invoices and draft tone-aware parent reminders in the Referee queue. Does not send anything.", "parameters": {"type": "OBJECT", "properties": {}}},
]


def _execute_tool(name: str, args: dict[str, Any]) -> Any:
    if name == "create_invoice":
        result = paypal_client.create_invoice(**{
            "client_name": args["client_name"], "client_email": args["client_email"],
            "description": args["description"], "amount": args["amount"],
            "currency": args.get("currency", "USD"), "due_in_days": args.get("due_in_days", 7),
        })
        # Link an invoice to a roster player only when one exact email match exists.
        email = args["client_email"].strip().casefold()
        matches = [p for p in roster_service.get_roster() if (p.get("parent_email") or "").casefold() == email]
        if len(matches) == 1 and result.get("id"):
            roster_service.link_invoice_to_player(str(result["id"]), matches[0])
        return result
    if name == "bulk_create_invoices":
        return roster_service.bulk_create_invoices(
            args["description"], args["amount"], args.get("due_in_days", 7), args.get("player_filter")
        )
    if name == "list_invoices":
        return paypal_client.list_invoices()
    if name == "get_summary":
        return paypal_client.get_summary()
    if name == "propose_action":
        return referee_queue.propose_action(args["action_type"], args["invoice_ids"], args.get("reminder_message"))
    if name == "chase_overdue":
        return referee_queue.chase_overdue()
    raise ValueError(f"Unknown Gemini tool: {name}")


def run_agent(
    user_message: str,
    history: list[dict[str, str]] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Send a chat turn to Gemini, execute read/draft/proposal tools, and return reply."""
    if progress_callback:
        progress_callback("Waiting for Gemini...")
    client, model = get_gemini_client()
    contents: list[types.Content] = []
    for turn in history or []:
        role = "user" if turn.get("role") == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=turn.get("content", ""))]))
    contents.append(types.Content(role="user", parts=[types.Part(text=user_message)]))
    actions: list[dict[str, Any]] = []

    # Gemini may request more than one tool round; cap it to avoid runaway loops.
    for _ in range(8):
        response = client.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                tools=[types.Tool(function_declarations=TOOLS)],
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                temperature=0.2,
            ),
        )
        candidate = response.candidates[0]
        model_content = candidate.content
        calls = [part.function_call for part in (model_content.parts or []) if part.function_call]
        contents.append(model_content)
        if not calls:
            reply = response.text or "I couldn't prepare a reply. Please try again."
            return {
                "reply": reply,
                "actions": actions,
                "history": (history or []) + [{"role": "user", "content": user_message}, {"role": "assistant", "content": reply}],
            }

        response_parts: list[types.Part] = []
        for call in calls:
            name = call.name or ""
            args = dict(call.args or {})
            if progress_callback:
                progress_callback(f"Preparing {name}...")
            try:
                result = _execute_tool(name, args)
                action = {"tool_name": name, "arguments": args, "result": result}
                response_payload = {"ok": True, "result": result}
            except Exception as exc:
                action = {"tool_name": name, "arguments": args, "error": str(exc)}
                response_payload = {"ok": False, "error": str(exc)}
            actions.append(action)
            response_parts.append(types.Part(function_response=types.FunctionResponse(
                name=name, response=response_payload, id=call.id
            )))
        # The current SDK guide specifies function responses as a user turn with
        # the matching call ID, paired with the model's function-call content.
        contents.append(types.Content(role="user", parts=response_parts))

    raise RuntimeError("Gemini requested too many tool rounds; please try a more focused request.")
