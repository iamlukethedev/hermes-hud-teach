"""Local IPC for the click-through overlay daemon."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import tempfile
from pathlib import Path
from typing import Any, Optional

PLUGIN_NAME = "hud-teach"
SOCKET_NAME = "overlay.sock"
PID_NAME = "overlay.pid"
HOME_ENV = "HUD_TEACH_HOME"
# macOS caps AF_UNIX paths at 104 bytes including the terminator.
MAX_SOCKET_PATH = 100


def state_dir() -> Path:
    """Profile-aware runtime directory; HUD_TEACH_HOME wins (the daemon and tests set it)."""
    env = os.environ.get(HOME_ENV)
    if env:
        path = Path(env)
    else:
        path = None
        try:
            from plugins.plugin_storage import plugin_data_dir

            path = Path(plugin_data_dir(PLUGIN_NAME))
        except Exception:
            path = None
        if path is None:
            base = os.environ.get("HERMES_HOME")
            if base:
                root = Path(base)
            else:
                try:
                    from hermes_constants import get_hermes_home

                    root = Path(get_hermes_home())
                except Exception:
                    root = Path.home() / ".hermes"
            path = root / "plugin-data" / PLUGIN_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def socket_path() -> Path:
    """Socket inside the state dir, or a short per-dir temp path when that would be too long."""
    base = state_dir()
    path = base / SOCKET_NAME
    if len(str(path).encode("utf-8")) <= MAX_SOCKET_PATH:
        return path
    digest = hashlib.sha1(str(base).encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"hud-teach-{digest}.sock"


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
    except (OSError, ValueError):
        return None
