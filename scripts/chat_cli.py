"""Talk to Huddle from a terminal without building a frontend."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from app.agent import run_agent  # noqa: E402


def main() -> None:
    history: list[dict[str, str]] = []
    print("Huddle is ready. Type 'exit' to stop.")

    def show_progress(message: str) -> None:
        print(f"\n{message}", flush=True)

    while True:
        try:
            message = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break
        if message.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        if not message:
            continue
        try:
            result = run_agent(message, history=history, progress_callback=show_progress)
        except KeyboardInterrupt:
            print("\nStopped this request. You can try again or type 'exit'.")
            continue
        except Exception as exc:
            print(f"Huddle error: {exc}")
            continue
        print(f"\nHuddle: {result['reply']}")
        for action in result.get("actions", []):
            print(f"  Prepared: {action['tool_name']} {action['arguments']}")
            if "result" in action:
                print(f"  Result: {action['result']}")
            else:
                print(f"  Error: {action['error']}")
        history = result.get("history", history)


if __name__ == "__main__":
    main()
