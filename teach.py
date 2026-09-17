"""teach_screen tool — list, capture, draw, or clear walkthrough marks."""

from __future__ import annotations

import base64
import importlib
import json
import platform
from typing import Any, Optional

try:
    from .shapes import validate_draw_payload
except ImportError:
    from shapes import validate_draw_payload


def _mod(name: str):
    if __package__:
        return importlib.import_module(f".{name}", __package__)
    return importlib.import_module(name)

ACTIONS = ("list", "capture", "draw", "clear", "status")


def macos_only() -> bool:
    return platform.system() == "Darwin"


def _error(message: str) -> str:
    return json.dumps({"ok": False, "error": message})


def _ok(payload: dict[str, Any]) -> str:
    body = {"ok": True, **payload}
    return json.dumps(body, ensure_ascii=False)


def handle_teach_screen(
    action: str = "status",
    target: Optional[str] = None,
    shapes: Any = None,
    frame_width: Any = None,
    frame_height: Any = None,
    bounds: Any = None,
    ttl_seconds: Any = None,
    **_kwargs: Any,
) -> Any:
    """Dispatch one teach_screen action."""
    if not macos_only():
        return _error("teach_screen is macOS-only in this release.")
    verb = (action or "status").strip().lower()
    if verb not in ACTIONS:
        return _error(f"action must be one of: {', '.join(ACTIONS)}.")

    if verb == "list":
        list_windows = _mod("capture").list_windows

        try:
            windows = list_windows()
        except Exception as exc:
            return _error(str(exc))
        return _ok({"windows": windows, "count": len(windows)})

    if verb == "status":
        status = _mod("overlay").status

        return _ok(status())

    if verb == "clear":
        clear = _mod("overlay").clear

        try:
            return _ok(clear())
        except Exception as exc:
            return _error(str(exc))

    if verb == "capture":
        capture_window = _mod("capture").capture_window

        try:
            shot = capture_window(target)
        except Exception as exc:
            return _error(str(exc))
        summary = (
            f"Captured {shot['app']}"
            + (f" — {shot['title']}" if shot.get("title") else "")
            + f" at {shot['frame_width']}x{shot['frame_height']} px. "
            "Draw with teach_screen action=draw using these frame_width/frame_height "
            "values and the bounds object. Coordinates are screenshot pixels."
        )
        b64 = base64.b64encode(shot["jpeg"]).decode("ascii")
        meta = {
            "app": shot["app"],
            "title": shot["title"],
            "bounds": shot["bounds"],
            "frame_width": shot["frame_width"],
            "frame_height": shot["frame_height"],
        }
        return {
            "_multimodal": True,
            "content": [
                {"type": "text", "text": json.dumps({"ok": True, **meta, "summary": summary})},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ],
            "text_summary": summary,
            "meta": meta,
        }

    if verb == "draw":
        problem = validate_draw_payload(shapes, frame_width, frame_height)
        if problem:
            return _error(problem)
        ttl = 180.0 if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0 or ttl > 900:
            return _error("ttl_seconds must be between 0 and 900.")
        if not isinstance(bounds, dict) or not bounds:
            return _error("draw needs bounds from the capture you just took (x, y, width, height).")
        draw = _mod("overlay").draw

        try:
            result = draw(
                bounds={
                    "x": int(bounds.get("x") or 0),
                    "y": int(bounds.get("y") or 0),
                    "width": int(bounds.get("width") or 0),
                    "height": int(bounds.get("height") or 0),
                },
                frame_width=float(frame_width),
                frame_height=float(frame_height),
                shapes=list(shapes),
                ttl_seconds=ttl,
            )
        except Exception as exc:
            return _error(str(exc))
        return _ok({"drawn": result.get("drawn"), "ttl_seconds": ttl})

    return _error(f"unhandled action {verb!r}")


SCHEMA = {
    "name": "teach_screen",
    "description": (
        "Teach on any live Mac window behind Hermes (chess, games, Photoshop, "
        "Settings): list windows, screenshot one, "
        "then draw numbered click-through marks on it. Use action=capture first "
        "(returns the image plus frame_width/frame_height/bounds), then action=draw "
        "with those numbers and shapes that include step 1–12. Leave the mouse to "
        "the user unless they asked you to click. New draw replaces the previous "
        "marks. ttl_seconds defaults to 180. macOS only; needs Screen Recording."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS),
                "description": "list, capture, draw, clear, or status.",
            },
            "target": {
                "type": "string",
                "description": "Optional app or window-title substring (e.g. Chess, Chrome, Photoshop).",
            },
            "shapes": {
                "type": "array",
                "description": "Marks to paint. Each needs kind plus geometry in screenshot pixels, optional step 1–12.",
            },
            "frame_width": {
                "type": "number",
                "description": "Pixel width of the capture the coordinates come from.",
            },
            "frame_height": {
                "type": "number",
                "description": "Pixel height of the capture the coordinates come from.",
            },
            "bounds": {
                "type": "object",
                "description": "DIP window rect from capture: x, y, width, height.",
            },
            "ttl_seconds": {
                "type": "number",
                "description": "How long marks stay up (default 180, max 900).",
            },
        },
        "required": ["action"],
    },
}
