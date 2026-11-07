"""/teach slash command and `hermes hud-teach` CLI: check, demo, status, clear."""

from __future__ import annotations

import importlib
import json
from typing import Any, Callable, Optional

SUBCOMMANDS = ("check", "demo", "status", "clear", "stop")
USAGE = (
    "Usage: /teach <check|demo [app]|status|clear|stop>\n"
    "  check   permissions, Tk and overlay health, with the fix for anything missing\n"
    "  demo    draw a sample lesson on the frontmost window (or the named app) for 30 s\n"
    "  status  what is on screen now and the last capture\n"
    "  clear   remove the marks\n"
    "  stop    clear and quit the overlay process"
)
CHECK_LABELS = {
    "macos": "macOS",
    "tk": "Tk for the overlay",
    "accessibility": "Accessibility (window names)",
    "screen_recording": "Screen Recording",
    "overlay": "Overlay process",
    "state_dir": "State directory",
}
DEMO_TTL = 30


def _mod(name: str):
    if __package__:
        return importlib.import_module(f".{name}", __package__)
    return importlib.import_module(name)


def format_check(report: dict[str, Any]) -> str:
    lines = ["HUD Teach is ready." if report.get("ready") else "HUD Teach needs setup:"]
    for key, label in CHECK_LABELS.items():
        item = report.get("checks", {}).get(key)
        if item is None:
            continue
        if key == "overlay":
            state = "running" if item.get("running") else "starts on first draw"
            lines.append(f"  ✓ {label}: {state}")
            continue
        mark = "✓" if item.get("ok") else "✗"
        extra = ""
        if key == "tk" and item.get("ok"):
            extra = f" (Tk {item.get('tk')})"
        if key == "accessibility" and item.get("ok"):
            extra = f" ({item.get('windows')} windows visible)"
        if key == "state_dir" and item.get("ok"):
            extra = f" ({item.get('path')})"
        lines.append(f"  {mark} {label}{extra}")
        if not item.get("ok") and item.get("fix"):
            lines.append(f"      fix: {item['fix']}")
    if report.get("note"):
        lines.append(f"Note: {report['note']}")
    return "\n".join(lines)


def demo_shapes(frame_width: float, frame_height: float) -> list[dict[str, Any]]:
    """Sample marks scaled to any capture: an outline, a target, and an arrow into it."""
    w, h = float(frame_width), float(frame_height)
    inset = max(8.0, min(w, h) * 0.03)
    cx, cy = w * 0.5, h * 0.55
    radius = max(18.0, min(w, h) * 0.08)
    return [
        {"kind": "rect", "x": inset, "y": inset, "width": w - 2 * inset, "height": h - 2 * inset,
         "color": "blue", "dashed": True, "step": 1, "label": "the window HUD Teach captured"},
        {"kind": "circle", "x": cx, "y": cy, "radius": radius, "color": "yellow", "step": 2,
         "label": "click here: the app still gets it"},
        {"kind": "arrow", "fromX": w * 0.2, "fromY": h * 0.85, "toX": cx - radius * 0.8, "toY": cy + radius * 0.6,
         "color": "red", "step": 3},
    ]


def run_demo(target: Optional[str] = None) -> str:
    capture = _mod("capture")
    teach = _mod("teach")
    if not teach.macos_only():
        return "The demo draws on macOS only. Run /teach check for details."
    try:
        shot = capture.capture_window(target or None)
    except Exception as exc:
        return f"Capture failed: {exc}\nRun /teach check to see what is missing."
    _mod("last_capture").save_capture(shot)
    raw = teach.handle_teach_screen(
        action="draw",
        shapes=demo_shapes(shot["frame_width"], shot["frame_height"]),
        title="HUD Teach is working",
        steps=[
            {"text": "Marks sit on the real window, not a screenshot.", "done": True},
            {"text": "Click the yellow ring: the app underneath still gets the click."},
            {"text": f"Marks clear themselves after {DEMO_TTL} s, or run /teach clear."},
        ],
        current_step=2,
        ttl_seconds=DEMO_TTL,
    )
    data = json.loads(raw)
    if not data.get("ok"):
        return f"Draw failed: {data.get('error')}\nRun /teach check to see what is missing."
    where = shot["app"] + (f" — {shot['title']}" if shot.get("title") else "")
    return f"Demo lesson drawn on {where} for {DEMO_TTL} s. Clear it early with /teach clear."


def run_status() -> str:
    data = json.loads(_mod("teach").handle_teach_screen(action="status"))
    if not data.get("ok"):
        return f"Status failed: {data.get('error')}"
    if not data.get("running"):
        line = "Overlay not running (it starts on the first draw)."
    elif data.get("visible"):
        parts = [f"{data.get('shapes', 0)} marks on screen"]
        if data.get("title"):
            parts.append(f"lesson {data['title']!r}")
        if data.get("current_step") and data.get("steps"):
            parts.append(f"step {data['current_step']} of {data['steps']}")
        if data.get("expires_in") is not None:
            parts.append(f"clears in {data['expires_in']} s")
        line = ", ".join(parts) + "."
    else:
        line = "Overlay running, nothing on screen."
    last = data.get("last_capture")
    if last:
        name = last.get("app") or "?"
        if last.get("title"):
            name += f" — {last['title']}"
        line += f"\nLast capture: {name}, {last.get('age_seconds')} s ago."
    return line


def run_clear() -> str:
    data = json.loads(_mod("teach").handle_teach_screen(action="clear"))
    if not data.get("ok"):
        return f"Clear failed: {data.get('error')}"
    return "Marks cleared." if data.get("cleared") else "Nothing to clear."


def run_stop() -> str:
    try:
        result = _mod("overlay").stop()
    except Exception as exc:
        return f"Stop failed: {exc}"
    return "Overlay stopped." if result.get("stopped") else "Overlay was not running."


def dispatch(raw_args: str) -> str:
    parts = (raw_args or "").strip().split(maxsplit=1)
    sub = parts[0].lower() if parts else ""
    rest = parts[1].strip() if len(parts) > 1 else ""
    handlers: dict[str, Callable[[], str]] = {
        "check": lambda: format_check(_mod("teach").run_check()),
        "demo": lambda: run_demo(rest or None),
        "status": run_status,
        "clear": run_clear,
        "stop": run_stop,
    }
    handler = handlers.get(sub)
    if handler is None:
        return USAGE
    try:
        return handler()
    except Exception as exc:
        return f"/teach {sub} failed: {exc}"


def slash_command(raw_args: str = "", **_kwargs: Any) -> str:
    return dispatch(raw_args)


def setup_cli(subparser) -> None:
    subs = subparser.add_subparsers(dest="hud_teach_command")
    subs.add_parser("check", help="Check permissions, Tk and the overlay")
    demo = subs.add_parser("demo", help="Draw a 30 s sample lesson on the frontmost window")
    demo.add_argument("target", nargs="?", default=None, help="App or window-title substring")
    subs.add_parser("status", help="Show what is on screen")
    subs.add_parser("clear", help="Remove the marks")
    subs.add_parser("stop", help="Clear and quit the overlay process")
    subparser.set_defaults(func=run_cli)


def run_cli(args) -> None:
    sub = getattr(args, "hud_teach_command", None) or ""
    target = getattr(args, "target", None)
    print(dispatch(f"{sub} {target}" if sub == "demo" and target else sub))
