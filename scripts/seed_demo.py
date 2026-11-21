"""Write a fictional Indian roster using the configured Sandbox email for three players."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.roster_service import seed_demo_roster  # noqa: E402


def main() -> None:
    result = seed_demo_roster()
    print(f"Saved {result['saved_count']} fictional players with ₹500 monthly fees to data/roster.json")
    print("The first three players use TEST_CLIENT_EMAIL; remaining example.com addresses are skipped during bulk billing.")


if __name__ == "__main__":
    main()
