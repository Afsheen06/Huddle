"""Write a fictional, non-billable 12-player demo roster to data/roster.json."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.roster_service import seed_demo_roster  # noqa: E402


def main() -> None:
    result = seed_demo_roster()
    print(f"Saved {result['saved_count']} fictional players to data/roster.json")
    print("All demo emails are blank. The demo roster cannot be bulk-billed until you add real Sandbox buyer emails.")


if __name__ == "__main__":
    main()
