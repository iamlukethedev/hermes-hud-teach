"""Remember the last capture so draw can reuse its geometry without the model copying numbers."""

from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any, Optional

try:
    from .ipc import state_dir
except ImportError:
    from ipc import state_dir

LAST_CAPTURE = "last_capture.json"
# Past this age a capture probably no longer matches what is on screen.
STALE_AFTER_SECONDS = 600.0


def _path() -> Path:
    return state_dir() / LAST_CAPTURE


def new_capture_id() -> str:
    return secrets.token_hex(4)


def save_capture(meta: dict[str, Any]) -> dict[str, Any]:
    """Persist geometry for the capture the model is looking at; returns the stored record."""
    record = {
        "capture_id": meta.get("capture_id") or new_capture_id(),
        "app": meta.get("app", ""),
        "title": meta.get("title", ""),
        "bounds": dict(meta.get("bounds") or {}),
        "frame_width": meta.get("frame_width"),
        "frame_height": meta.get("frame_height"),
        "display": bool(meta.get("display")),
        "captured_at": time.time(),
    }
    path = _path()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record), encoding="utf-8")
    os.replace(tmp, path)
    return record


def load_capture() -> Optional[dict[str, Any]]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def capture_age(record: dict[str, Any]) -> float:
    try:
        return max(0.0, time.time() - float(record.get("captured_at") or 0))
    except (TypeError, ValueError):
        return float("inf")


def forget_capture() -> None:
    try:
        _path().unlink()
    except OSError:
        pass
