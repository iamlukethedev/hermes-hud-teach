"""REST door for the desktop half: live status for the chip, clear, and setup check."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from teach import handle_teach_screen  # noqa: E402

router = APIRouter()


def _call(action: str) -> dict:
    try:
        return json.loads(handle_teach_screen(action=action))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@router.get("/status")
def marks_status() -> dict:
    """What the overlay is showing now, for the status-bar chip."""
    return _call("status")


@router.post("/clear")
def clear_marks() -> dict:
    """Drop the current overlay without waiting for TTL."""
    return _call("clear")


@router.get("/check")
def setup_check() -> dict:
    """Permissions, Tk and overlay health, each with its fix."""
    return _call("check")
