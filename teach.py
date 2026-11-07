"""teach_screen tool — list, capture, draw, clear, status, or check walkthrough marks."""

from __future__ import annotations

import base64
import importlib
import json
import platform
import subprocess
import sys
from typing import Any, Optional

try:
    from .shapes import (
        COLORS,
        KINDS,
        LEGEND_POSITIONS,
        MAX_STEP,
        normalize_steps,
        validate_draw_payload,
        validate_lesson,
    )
except ImportError:
    from shapes import COLORS, KINDS, LEGEND_POSITIONS, MAX_STEP, normalize_steps, validate_draw_payload, validate_lesson

PLUGIN_NAME = "hud-teach"
ACTIONS = ("list", "capture", "draw", "clear", "status", "check")
DEFAULT_TTL = 180.0
MAX_TTL = 900.0
# A window that changed size has reflowed; old coordinates no longer point at the same controls.
RESIZE_TOLERANCE = 2


def _mod(name: str):
    if __package__:
        return importlib.import_module(f".{name}", __package__)
    return importlib.import_module(name)


def macos_only() -> bool:
    return platform.system() == "Darwin"


def _error(message: str, **extra: Any) -> str:
    return json.dumps({"ok": False, "error": message, **extra}, ensure_ascii=False)


def _ok(payload: dict[str, Any]) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False)


def _notify_desktop(event: str, payload: dict[str, Any]) -> None:
    """Tell a connected Hermes Desktop that the marks changed; a no-op everywhere else."""
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event

        broadcast_plugin_event(PLUGIN_NAME, event, payload)
    except Exception:
        pass


def _int_bounds(raw: dict[str, Any]) -> dict[str, int]:
    return {k: int(raw.get(k) or 0) for k in ("x", "y", "width", "height")}


def _window_rows(windows: list[dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]:
    return [{"app": w.get("app", ""), "title": w.get("title", "")} for w in windows[:limit]]


def _check_tk() -> dict[str, Any]:
    probe = "import tkinter; tkinter.Tcl(); print(tkinter.TkVersion)"
    try:
        proc = subprocess.run(
            [sys.executable, "-c", probe], capture_output=True, text=True, timeout=10, check=False
        )
    except Exception as exc:
        return {"ok": False, "python": sys.executable, "detail": str(exc)[:300]}
    if proc.returncode == 0:
        return {"ok": True, "python": sys.executable, "tk": proc.stdout.strip()}
    return {
        "ok": False,
        "python": sys.executable,
        "fix": "Run Hermes on a Python that includes Tk (python.org, Homebrew python-tk, or uv builds).",
        "detail": (proc.stderr or "").strip()[-300:],
    }


def run_check() -> dict[str, Any]:
    """Everything a first run needs, with the fix for anything missing."""
    checks: dict[str, Any] = {"macos": {"ok": macos_only(), "platform": platform.system()}}
    if not macos_only():
        checks["macos"]["fix"] = "teach_screen draws on macOS only; run Hermes on a Mac."
    checks["tk"] = _check_tk()
    if macos_only():
        checks.update(_mod("capture").check_permissions())
    try:
        checks["overlay"] = {"ok": True, **{k: v for k, v in _mod("overlay").status().items() if k != "ok"}}
    except Exception as exc:
        checks["overlay"] = {"ok": False, "detail": str(exc)[:300]}
    try:
        checks["state_dir"] = {"ok": True, "path": str(_mod("ipc").state_dir())}
    except Exception as exc:
        checks["state_dir"] = {"ok": False, "detail": str(exc)[:300]}
    required = ("macos", "tk", "screen_recording", "state_dir")
    ready = all(checks.get(name, {}).get("ok") for name in required)
    next_steps = [c["fix"] for c in checks.values() if not c.get("ok") and c.get("fix")]
    report = {"ready": ready, "checks": checks, "next_steps": next_steps}
    if checks.get("screen_recording", {}).get("ok"):
        report["note"] = (
            "Screen Recording ok means screencapture ran. If captures show only the wallpaper, "
            "it is still off for this app; toggle it and restart the app."
        )
    return report


def _capture(target: Optional[str]) -> Any:
    capture = _mod("capture")
    try:
        shot = capture.capture_window(target)
    except capture.WindowNotFound as exc:
        return _error(str(exc), windows=_window_rows(exc.windows))
    except Exception as exc:
        return _error(str(exc))
    record = _mod("last_capture").save_capture(shot)
    where = f"{shot['app']}" + (f" — {shot['title']}" if shot.get("title") else "")
    summary = (
        f"Captured {where} at {shot['frame_width']}x{shot['frame_height']} px "
        f"(capture_id {record['capture_id']}). Draw with teach_screen action=draw; frame size and "
        "bounds default to this capture. Coordinates are pixels in this image, (0, 0) top-left."
    )
    if shot.get("display") and shot.get("window_error"):
        summary += " Window list unavailable, so this is the whole main display."
    meta = {
        "capture_id": record["capture_id"],
        "app": shot["app"],
        "title": shot["title"],
        "bounds": shot["bounds"],
        "frame_width": shot["frame_width"],
        "frame_height": shot["frame_height"],
        "display": bool(shot.get("display")),
    }
    b64 = base64.b64encode(shot["jpeg"]).decode("ascii")
    return {
        "_multimodal": True,
        "content": [
            {"type": "text", "text": json.dumps({"ok": True, **meta, "summary": summary}, ensure_ascii=False)},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        ],
        "text_summary": summary,
        "meta": meta,
    }


def _resolve_geometry(
    capture_id: Optional[str], frame_width: Any, frame_height: Any, bounds: Any
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Merge explicit geometry over the last capture; returns (geometry, error)."""
    last = _mod("last_capture").load_capture()
    if capture_id and (not last or last.get("capture_id") != capture_id):
        return None, (
            f"capture_id {capture_id!r} is not the latest capture. Capture again and draw on what "
            "the new screenshot shows."
        )
    explicit = bounds is not None or frame_width is not None or frame_height is not None
    if not last and not explicit:
        return None, "Nothing captured yet. Call teach_screen action=capture first, then draw."
    base = last or {}
    geo = {
        "frame_width": frame_width if frame_width is not None else base.get("frame_width"),
        "frame_height": frame_height if frame_height is not None else base.get("frame_height"),
        "bounds": bounds if bounds is not None else base.get("bounds"),
        "app": base.get("app", "") if bounds is None else "",
        "title": base.get("title", "") if bounds is None else "",
        "display": bool(base.get("display")) if bounds is None else False,
        "from_capture": bounds is None and bool(last),
        "age": _mod("last_capture").capture_age(base) if last else None,
    }
    if not isinstance(geo["bounds"], dict) or not geo["bounds"]:
        return None, "draw needs bounds from the capture you just took (x, y, width, height)."
    return geo, None


def _follow_window(geo: dict[str, Any]) -> tuple[dict[str, int], list[str], Optional[str]]:
    """Track the captured window to where it is now; refuse if it was resized."""
    bounds = _int_bounds(geo["bounds"])
    if not geo.get("from_capture") or geo.get("display") or not geo.get("app"):
        return bounds, [], None
    capture = _mod("capture")
    try:
        windows = capture.list_windows()
    except Exception:
        return bounds, ["Could not re-check the window position; drawing where it was captured."], None
    now = capture.find_window(windows, geo["app"], geo.get("title", ""))
    if not now:
        return bounds, [f"{geo['app']} window not found now; drawing where it was captured."], None
    current = _int_bounds(now)
    if (
        abs(current["width"] - bounds["width"]) > RESIZE_TOLERANCE
        or abs(current["height"] - bounds["height"]) > RESIZE_TOLERANCE
    ):
        return bounds, [], (
            f"{geo['app']} was resized since the capture ({bounds['width']}x{bounds['height']} → "
            f"{current['width']}x{current['height']}), so the marks would miss. Capture again."
        )
    notes = []
    if current["x"] != bounds["x"] or current["y"] != bounds["y"]:
        notes.append(f"{geo['app']} moved since the capture; marks follow it.")
    return current, notes, None


def _draw(
    shapes: Any,
    frame_width: Any,
    frame_height: Any,
    bounds: Any,
    ttl_seconds: Any,
    title: Any,
    steps: Any,
    current_step: Any,
    legend_position: Any,
    capture_id: Optional[str],
) -> str:
    problem = validate_lesson(title, steps, current_step, legend_position)
    if problem:
        return _error(problem)
    try:
        ttl = DEFAULT_TTL if ttl_seconds is None else float(ttl_seconds)
    except (TypeError, ValueError):
        return _error("ttl_seconds must be a number.")
    if ttl <= 0 or ttl > MAX_TTL:
        return _error(f"ttl_seconds must be between 0 and {MAX_TTL:g}.")
    geo, problem = _resolve_geometry(capture_id, frame_width, frame_height, bounds)
    if problem or geo is None:
        return _error(problem or "draw could not resolve the capture geometry.")
    problem = validate_draw_payload(shapes, geo["frame_width"], geo["frame_height"])
    if problem:
        return _error(problem)
    target_bounds, notes, problem = _follow_window(geo)
    if problem:
        return _error(problem)
    age = geo.get("age")
    if age is not None and age > _mod("last_capture").STALE_AFTER_SECONDS:
        notes.append(f"The capture is {int(age // 60)} minutes old; capture again if the screen changed.")
    lesson_steps = normalize_steps(steps)
    try:
        result = _mod("overlay").draw(
            bounds=target_bounds,
            frame_width=float(geo["frame_width"]),
            frame_height=float(geo["frame_height"]),
            shapes=list(shapes),
            ttl_seconds=ttl,
            title=title.strip() if isinstance(title, str) and title.strip() else None,
            steps=lesson_steps,
            current_step=current_step,
            legend_position=legend_position or "auto",
        )
    except Exception as exc:
        return _error(str(exc))
    if not result.get("ok", True):
        return _error(str(result.get("error") or "overlay refused the draw"))
    payload = {
        "drawn": result.get("drawn"),
        "ttl_seconds": ttl,
        "app": geo.get("app") or None,
        "title": result.get("title"),
        "steps": len(lesson_steps),
        "current_step": current_step,
        "legend": result.get("legend"),
    }
    if notes:
        payload["notes"] = notes
    _notify_desktop("marks.changed", {"visible": True, **{k: payload[k] for k in ("drawn", "title", "steps", "current_step")}})
    return _ok(payload)


def handle_teach_screen(
    action: str = "status",
    target: Optional[str] = None,
    shapes: Any = None,
    frame_width: Any = None,
    frame_height: Any = None,
    bounds: Any = None,
    ttl_seconds: Any = None,
    title: Any = None,
    steps: Any = None,
    current_step: Any = None,
    legend_position: Any = None,
    capture_id: Optional[str] = None,
    **_kwargs: Any,
) -> Any:
    """Dispatch one teach_screen action."""
    verb = (action or "status").strip().lower()
    if verb not in ACTIONS:
        return _error(f"action must be one of: {', '.join(ACTIONS)}.")

    if verb == "check":
        try:
            return _ok(run_check())
        except Exception as exc:
            return _error(str(exc))

    if verb == "status":
        try:
            body = _mod("overlay").status()
        except Exception as exc:
            return _error(str(exc))
        last = _mod("last_capture").load_capture()
        if last:
            body["last_capture"] = {
                "capture_id": last.get("capture_id"),
                "app": last.get("app"),
                "title": last.get("title"),
                "age_seconds": int(_mod("last_capture").capture_age(last)),
            }
        return _ok({k: v for k, v in body.items() if k != "ok"})

    if not macos_only():
        return _error("teach_screen draws on macOS only. Run action=check for details.")

    if verb == "list":
        capture = _mod("capture")
        try:
            windows = capture.list_windows()
        except Exception as exc:
            return _error(str(exc))
        return _ok({"windows": windows, "count": len(windows)})

    if verb == "clear":
        try:
            result = _mod("overlay").clear()
        except Exception as exc:
            return _error(str(exc))
        _notify_desktop("marks.changed", {"visible": False})
        return _ok({k: v for k, v in result.items() if k != "ok"})

    if verb == "capture":
        return _capture(target)

    return _draw(
        shapes, frame_width, frame_height, bounds, ttl_seconds,
        title, steps, current_step, legend_position, capture_id,
    )


_POINT = {
    "type": "object",
    "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
    "required": ["x", "y"],
}

SHAPE_SCHEMA = {
    "type": "object",
    "description": (
        "One mark in screenshot pixels. circle: x, y, radius. rect: x, y, width, height. "
        "arrow/line: fromX, fromY, toX, toY (arrow points at to). polyline: points. "
        "label: x, y, text."
    ),
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "step": {"type": "integer", "minimum": 1, "maximum": MAX_STEP, "description": "Badge number 1–12."},
        "color": {"type": "string", "enum": list(COLORS), "description": "Default red."},
        "label": {"type": "string", "description": "Short caption beside the badge (≤80 chars)."},
        "dashed": {"type": "boolean", "description": "Dashed outline, e.g. for an optional step."},
        "fill": {"type": "boolean", "description": "rect only: darken the inside."},
        "x": {"type": "number"},
        "y": {"type": "number"},
        "radius": {"type": "number"},
        "width": {"type": "number"},
        "height": {"type": "number"},
        "fromX": {"type": "number"},
        "fromY": {"type": "number"},
        "toX": {"type": "number"},
        "toY": {"type": "number"},
        "points": {"type": "array", "items": _POINT},
        "text": {"type": "string", "description": "label kind only."},
    },
    "required": ["kind"],
}

SCHEMA = {
    "name": "teach_screen",
    "description": (
        "Teach on any live Mac window behind Hermes (chess, games, Photoshop, Settings, a "
        "browser): screenshot it, then paint numbered click-through marks and an on-screen "
        "step card on the real UI. Flow: action=capture (optional target app/window name) → "
        "look at the image → action=draw with shapes in that image's pixel coordinates; frame "
        "size and bounds default to the last capture. For a lesson, pass title, steps (short "
        "instructions) and current_step: the card lists them and the current step's badge "
        "pulses. After the user does a step and the screen changes, capture again and draw the "
        "next one with earlier steps marked done. A new draw replaces the old marks. Leave the "
        "mouse to the user unless they asked you to click. Run action=check when capture or "
        "draw fails. macOS only; needs Screen Recording."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(ACTIONS),
                "description": "capture, draw, clear, list (windows), status, or check (setup diagnostics).",
            },
            "target": {
                "type": "string",
                "description": "capture: app or window-title substring (e.g. Chess, Safari, Photoshop). Default: the frontmost app's largest window.",
            },
            "shapes": {
                "type": "array",
                "description": "draw: up to 24 marks, coordinates in pixels of the last capture.",
                "items": SHAPE_SCHEMA,
            },
            "title": {"type": "string", "description": "draw: lesson title shown on the step card (≤80 chars)."},
            "steps": {
                "type": "array",
                "description": "draw: up to 12 short instructions for the step card, in order. Set done=true on steps the user has finished.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "One instruction (≤120 chars)."},
                        "done": {"type": "boolean"},
                    },
                    "required": ["text"],
                },
            },
            "current_step": {
                "type": "integer",
                "minimum": 1,
                "maximum": MAX_STEP,
                "description": "draw: the step the user should do now; highlighted on the card, its badge pulses.",
            },
            "legend_position": {
                "type": "string",
                "enum": list(LEGEND_POSITIONS),
                "description": "draw: corner for the step card. auto picks the corner with the fewest marks.",
            },
            "capture_id": {
                "type": "string",
                "description": "draw: optional id from capture; refuses to draw if a newer capture replaced it.",
            },
            "frame_width": {
                "type": "number",
                "description": "draw: override the capture's pixel width (normally omitted).",
            },
            "frame_height": {
                "type": "number",
                "description": "draw: override the capture's pixel height (normally omitted).",
            },
            "bounds": {
                "type": "object",
                "description": "draw: override the window rect in screen points (normally omitted).",
                "properties": {
                    "x": {"type": "number"},
                    "y": {"type": "number"},
                    "width": {"type": "number"},
                    "height": {"type": "number"},
                },
            },
            "ttl_seconds": {
                "type": "number",
                "description": "draw: seconds the marks stay up (default 180, max 900).",
            },
        },
        "required": ["action"],
    },
}
