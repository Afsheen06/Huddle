"""Small JSON-file storage helpers for local Huddle demo data."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
_storage_lock = threading.RLock()
_RUNTIME_FILE_DEFAULTS = {
    "roster.json": [],
    "invoice_map.json": {},
    "manual_payments.json": {},
    "queue.json": [],
}


def ensure_data_files() -> None:
    """Create missing runtime JSON files without replacing any existing data.

    Render's free filesystem is temporary, so a fresh instance must be able to
    start with an empty roster, invoice map, and referee queue. Writes use the
    same atomic replace helper as normal updates.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _storage_lock:
        for filename, default in _RUNTIME_FILE_DEFAULTS.items():
            if not data_path(filename).exists():
                write_json(filename, default)


def data_path(filename: str) -> Path:
    """Resolve an application-owned JSON filename inside data/."""
    if Path(filename).name != filename or not filename.endswith(".json"):
        raise ValueError("Storage filename must be a simple .json filename.")
    return DATA_DIR / filename


def read_json(filename: str, default: Any) -> Any:
    """Read one local JSON file, returning a fresh default if it is absent."""
    path = data_path(filename)
    with _storage_lock:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)


def write_json(filename: str, value: Any) -> None:
    """Atomically replace a JSON file so interruption cannot leave half a file."""
    path = data_path(filename)
    with _storage_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=DATA_DIR,
                prefix=f".{path.stem}-",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_name = handle.name
                json.dump(value, handle, indent=2, ensure_ascii=False)
                handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if temp_name and os.path.exists(temp_name):
                os.unlink(temp_name)
