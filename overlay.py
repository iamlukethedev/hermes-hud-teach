"""Start and talk to the overlay daemon."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

try:
    from .ipc import ping, send, socket_path
except ImportError:
    from ipc import ping, send, socket_path


def _daemon_script() -> Path:
    return Path(__file__).resolve().parent / "overlay_daemon.py"


def ensure_daemon() -> None:
    """Start the overlay process if a ping does not succeed."""
    if ping() is not None:
        return
    sock = socket_path()
    if sock.exists():
        try:
            sock.unlink()
        except OSError:
            pass
    import subprocess

    env = os.environ.copy()
    subprocess.Popen(
        [sys.executable, str(_daemon_script())],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    deadline = time.time() + 4.0
    while time.time() < deadline:
        if ping() is not None:
            return
        time.sleep(0.1)
    raise RuntimeError("Overlay daemon did not start. Tk/Tcl may be missing from this Python.")


def draw(*, bounds: dict[str, int], frame_width: float, frame_height: float, shapes: list[dict[str, Any]], ttl_seconds: float) -> dict[str, Any]:
    ensure_daemon()
    return send(
        {
            "op": "draw",
            "bounds": bounds,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "shapes": shapes,
            "ttl_seconds": ttl_seconds,
        },
        timeout=3.0,
    )


def clear() -> dict[str, Any]:
    if ping() is None:
        return {"ok": True, "cleared": False, "note": "overlay was not running"}
    return send({"op": "clear"})


def status() -> dict[str, Any]:
    alive = ping()
    if alive is None:
        return {"ok": True, "running": False}
    return {"ok": True, "running": True, **{k: v for k, v in alive.items() if k != "ok"}}
