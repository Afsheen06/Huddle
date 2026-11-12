"""Assign two local PayPal Sandbox buyer emails to the first two demo players."""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.roster_service import get_roster, save_roster  # noqa: E402


def main() -> None:
    """Prompt locally for buyer emails; no email needs to be shared in chat."""
    players = get_roster()
    if len(players) < 2:
        print("Load the demo roster first by running: python scripts/seed_demo.py")
        return

    print("Enter the two Sandbox PERSONAL account emails you want to use as invoice recipients.")
    print("These will be assigned to the first two sample players shown below.")
    for index, player in enumerate(players[:2], start=1):
        print(f"{index}. {player['player_name']} (parent: {player.get('parent_name') or 'not set'})")

    recipients: list[tuple[str, str]] = []
    for index in range(2):
        parent_name = input(f"Name shown on Sandbox account for {players[index]['player_name']}'s parent: ").strip()
        while not parent_name:
            parent_name = input("Please type the account holder's name: ").strip()
        while True:
            email = input(f"Sandbox Personal email for {players[index]['player_name']}: ").strip()
            if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
                recipients.append((parent_name, email))
                break
            print("That doesn't look like an email address. Please try again.")

    # Keep the demo names, but clear placeholder emails on all other players so
    # bulk billing skips them instead of trying fictional example.com addresses.
    for index, player in enumerate(players):
        if index < 2:
            player["parent_name"], player["parent_email"] = recipients[index]
        else:
            player["parent_email"] = None
    result = save_roster(players)
    print(f"Updated the roster. {result['saved_count']} players remain; only the first 2 have Sandbox emails.")
    print("The other 10 will be skipped during bulk draft creation because their email is missing.")
    print("No invoice was created or sent by this script.")


if __name__ == "__main__":
    main()
