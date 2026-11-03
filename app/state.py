"""
state.py — Persistence layer for SCI Case Monitor.

Manages two JSON files stored in ~/.sci_monitor/:
  - config.json      : case configurations + app preferences
  - seen_orders.json : per-case set of already-seen order identifiers
"""

import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Storage directory
# ---------------------------------------------------------------------------
DATA_DIR = Path.home() / ".sci_monitor"
CONFIG_FILE = DATA_DIR / "config.json"
SEEN_ORDERS_FILE = DATA_DIR / "seen_orders.json"

_DEFAULT_CASE = {"case_type": "", "case_no": "", "year": ""}

_DEFAULT_CONFIG: dict[str, Any] = {
    "cases": [
        dict(_DEFAULT_CASE),
        dict(_DEFAULT_CASE),
        dict(_DEFAULT_CASE),
    ],
    "check_interval": 120,   # seconds
    "monitor_running": False,
}


def _ensure_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config() -> dict[str, Any]:
    """Return saved config, merging with defaults for any missing keys."""
    _ensure_dir()
    if CONFIG_FILE.exists():
        try:
            with CONFIG_FILE.open("r", encoding="utf-8") as fh:
                saved = json.load(fh)
            # Merge top-level defaults
            merged = dict(_DEFAULT_CONFIG)
            merged.update(saved)
            # Ensure cases list has exactly 3 entries
            cases = merged.get("cases", [])
            while len(cases) < 3:
                cases.append(dict(_DEFAULT_CASE))
            merged["cases"] = cases[:3]
            return merged
        except Exception:
            pass
    return {
        "cases": [dict(_DEFAULT_CASE) for _ in range(3)],
        "check_interval": 120,
        "monitor_running": False,
    }


def save_config(config: dict[str, Any]) -> None:
    _ensure_dir()
    with CONFIG_FILE.open("w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)


# ---------------------------------------------------------------------------
# Seen-orders helpers
# ---------------------------------------------------------------------------

def load_seen_orders() -> dict[str, list[str]]:
    """Return {case_key: [order_id, ...]} mapping."""
    _ensure_dir()
    if SEEN_ORDERS_FILE.exists():
        try:
            with SEEN_ORDERS_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {}


def save_seen_orders(seen: dict[str, list[str]]) -> None:
    _ensure_dir()
    with SEEN_ORDERS_FILE.open("w", encoding="utf-8") as fh:
        json.dump(seen, fh, indent=2)


def make_case_key(case_type: str, case_no: str, year: str) -> str:
    """Stable string key for a case triple."""
    return f"{case_type}_{case_no}_{year}"
