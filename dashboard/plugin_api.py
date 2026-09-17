"""REST door for the desktop half — clear leftover marks from the palette."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import APIRouter

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from overlay import clear  # noqa: E402

router = APIRouter()


@router.post("/clear")
def clear_marks() -> dict:
    """Drop the current overlay without waiting for TTL."""
    try:
        return {"ok": True, **clear()}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
