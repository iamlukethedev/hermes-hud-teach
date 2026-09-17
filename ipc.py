"""Local IPC for the click-through overlay daemon."""

from __future__ import annotations

import json
import os
import socket
from pathlib import Path
from typing import Any, Optional

SOCKET_NAME = "overlay.sock"
PID_NAME = "overlay.pid"


def state_dir() -> Path:
    """Profile-aware state directory; HUD_TEACH_HOME wins for tests."""
    env = os.environ.get("HUD_TEACH_HOME") or os.environ.get("HERMES_HOME")
    if env:
        base = Path(env)
    else:
        try:
            from hermes_constants import get_hermes_home

            base = get_hermes_home()
        except Exception:
            base = Path.home() / ".hermes"
    path = base / "hud-teach"
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    return state_dir() / SOCKET_NAME


def pid_path() -> Path:
    return state_dir() / PID_NAME


def send(payload: dict[str, Any], timeout: float = 2.0) -> dict[str, Any]:
    """Send one JSON object to the overlay daemon and return its reply."""
    path = str(socket_path())
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
        sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        raw = b""
        while not raw.endswith(b"\n"):
            chunk = sock.recv(4096)
            if not chunk:
                break
            raw += chunk
    finally:
        sock.close()
    if not raw:
        raise ConnectionError("overlay daemon returned an empty reply")
    reply = json.loads(raw.decode("utf-8"))
    if not isinstance(reply, dict):
        raise ConnectionError("overlay daemon returned a non-object reply")
    return reply


def ping() -> Optional[dict[str, Any]]:
    try:
        return send({"op": "ping"}, timeout=0.4)
    except OSError:
        return None
