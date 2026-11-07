"""Start and talk to the overlay daemon."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

try:
    from .ipc import HOME_ENV, ping, send, socket_path, state_dir
except ImportError:
    from ipc import HOME_ENV, ping, send, socket_path, state_dir


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
    env = os.environ.copy()
    # Pin the daemon to the directory this process resolved, so both sides agree on the socket.
    env[HOME_ENV] = str(state_dir())
    subprocess.Popen(
        [sys.executable, str(_daemon_script())],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        env=env,
    )
    deadline = time.time() + 5.0
    while time.time() < deadline:
        if ping() is not None:
            return
        time.sleep(0.1)
    raise RuntimeError(
        "Overlay daemon did not start. This Python may lack Tk/Tcl "
        f"({sys.executable}); the python.org, Homebrew python-tk and uv builds include it."
    )


def draw(
    *,
    bounds: dict[str, int],
    frame_width: float,
    frame_height: float,
    shapes: list[dict[str, Any]],
    ttl_seconds: float,
    title: Optional[str] = None,
    steps: Optional[list[dict[str, Any]]] = None,
    current_step: Optional[int] = None,
    legend_position: str = "auto",
) -> dict[str, Any]:
    ensure_daemon()
    return send(
        {
            "op": "draw",
            "bounds": bounds,
            "frame_width": frame_width,
            "frame_height": frame_height,
            "shapes": shapes,
            "ttl_seconds": ttl_seconds,
            "title": title,
            "steps": steps or [],
            "current_step": current_step,
            "legend_position": legend_position,
        },
        timeout=3.0,
    )


def clear() -> dict[str, Any]:
    if ping() is None:
        return {"ok": True, "cleared": False, "note": "overlay was not running"}
    return send({"op": "clear"})


def status() -> dict[str, Any]:
    if ping() is None:
        return {"ok": True, "running": False, "visible": False}
    try:
        reply = send({"op": "status"}, timeout=1.0)
    except (OSError, ValueError):
        return {"ok": True, "running": True}
    return {"ok": True, "running": True, **{k: v for k, v in reply.items() if k != "ok"}}


def stop() -> dict[str, Any]:
    if ping() is None:
        return {"ok": True, "stopped": False}
    return send({"op": "quit"})
