"""FastAPI routes for Huddle chat, roster, Referee queue, and club board."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from fastapi.responses import JSONResponse

from app import agent, paypal_client, referee_queue, roster_service
from app.storage import ensure_data_files
from app.settings import CLUB_NAME, CLUB_UPI_ID, CURRENCY_SYMBOL, DEFAULT_CURRENCY, PAYPAL_TEST_CURRENCY, UPI_ID_IS_PLACEHOLDER

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _cors_origins() -> list[str]:
    """Read allowed browser origins from a comma-separated environment value."""
    configured = os.getenv("CORS_ORIGINS", "")
    if configured.strip():
        return [origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()]
    # Vite's local dev address. Render receives its frontend URL via render.yaml.
    return ["http://localhost:5173", "http://127.0.0.1:5173"]


class PerIpRateLimitMiddleware:
    """A small process-local sliding-window limit for public AI-heavy routes.

    This is pure ASGI middleware (rather than Starlette's BaseHTTPMiddleware)
    to avoid wrapping request streams and to keep behavior predictable on Render.
    """

    def __init__(self, app, limit: int = 20, window_seconds: int = 60):
        self.app = app
        self.limit = limit
        self.window_seconds = window_seconds
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        method = scope.get("method", "")
        if path not in {"/chat", "/roster/parse"} or method != "POST":
            return await self.app(scope, receive, send)

        # Uvicorn's proxy-header handling supplies the visitor address on Render.
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        key = (path, client_ip)
        now = time.monotonic()
        with self.lock:
            hits = self.hits[key]
            while hits and now - hits[0] >= self.window_seconds:
                hits.popleft()
            if len(hits) >= self.limit:
                retry_after = max(1, int(self.window_seconds - (now - hits[0])))
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Please wait a minute and try again."},
                    headers={"Retry-After": str(retry_after)},
                )
                return await response(scope, receive, send)
            hits.append(now)

            # Expire old IP buckets periodically so this demo limiter stays small.
            if len(self.hits) > 500 and int(now) % 30 == 0:
                for stale_key, stale_hits in list(self.hits.items()):
                    while stale_hits and now - stale_hits[0] >= self.window_seconds:
                        stale_hits.popleft()
                    if not stale_hits:
                        self.hits.pop(stale_key, None)
        return await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Create empty local JSON files when a fresh Render instance starts."""
    ensure_data_files()
    yield


app = FastAPI(title="Huddle: AI Treasurer for Sports Clubs", version="1.1.0", lifespan=lifespan)
# Add the limiter first so CORS remains the outer middleware and adds headers to 429s.
app.add_middleware(PerIpRateLimitMiddleware, limit=20, window_seconds=60)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class HistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[HistoryTurn] | None = Field(default=None, max_length=30)


class RosterParseRequest(BaseModel):
    raw_text: str = Field(
        min_length=1,
        max_length=20000,
        description="Pasted roster text to extract (up to 20,000 characters).",
    )


class RosterSaveRequest(BaseModel):
    players: list[roster_service.RosterPlayer]


class RejectRequest(BaseModel):
    reason: str | None = None


class MarkPaidRequest(BaseModel):
    player_key: str = Field(min_length=1, max_length=500)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    """Return the agent reply, tool actions, fresh queue items, and chat history."""
    try:
        before = {item["id"] for item in referee_queue.get_queue()}
        result = agent.run_agent(request.message, [turn.model_dump() for turn in (request.history or [])])
        result["queue_items_created"] = [
            item for item in referee_queue.get_queue() if item.get("id") not in before
        ]
        return result
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/invoices")
def invoices() -> dict:
    try:
        return roster_service.list_linked_invoices()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/summary")
def summary() -> dict:
    try:
        return roster_service.get_fee_summary()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/roster/parse")
def parse_roster(request: RosterParseRequest) -> dict:
    """Extract a reviewable roster; this route does not save it."""
    try:
        return roster_service.parse_roster(request.raw_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/roster/save")
def save_roster(request: RosterSaveRequest) -> dict:
    try:
        return roster_service.save_roster([player.model_dump() for player in request.players])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/roster")
def get_roster() -> dict:
    return {"players": roster_service.get_roster()}


@app.get("/config")
def public_config() -> dict:
    """Non-secret display settings needed by the browser."""
    return {"currency_symbol": CURRENCY_SYMBOL, "default_currency": DEFAULT_CURRENCY,
            "paypal_test_currency": PAYPAL_TEST_CURRENCY, "club_name": CLUB_NAME,
            "upi_id": CLUB_UPI_ID, "upi_is_placeholder": UPI_ID_IS_PLACEHOLDER}


@app.get("/roster/{player_key}/payment")
def player_payment(player_key: str) -> dict:
    try:
        return roster_service.get_player_payment(player_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/roster/mark-paid")
def mark_paid(request: MarkPaidRequest) -> dict:
    try:
        return roster_service.mark_player_paid(request.player_key)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/demo/seed")
def seed_demo() -> dict:
    """Replace the local roster with Indian demo players and fake emails."""
    result = roster_service.seed_demo_roster()
    return {"saved_count": result["saved_count"], "message": "Indian demo roster loaded with fake example.com emails; replace them before PayPal Sandbox billing."}


@app.post("/demo/reset")
def reset_demo() -> dict:
    """Clear Huddle's local demo records and restore the fictional sample team."""
    referee_queue.clear_queue()
    return roster_service.reset_demo_data()


@app.get("/queue")
def get_queue() -> dict:
    return {"items": referee_queue.get_queue()}


@app.post("/queue/{queue_id}/approve")
def approve_queue_item(queue_id: str) -> dict:
    try:
        return referee_queue.approve_action(queue_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/queue/{queue_id}/reject")
def reject_queue_item(queue_id: str, request: RejectRequest | None = None) -> dict:
    try:
        return referee_queue.reject_action(queue_id, request.reason if request else None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/queue/approve-all")
def approve_all_queue_items() -> dict:
    try:
        return referee_queue.approve_all()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/board")
def board() -> dict:
    try:
        return roster_service.build_board()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
