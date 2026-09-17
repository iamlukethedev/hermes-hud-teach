#!/usr/bin/env python3
"""Click-through always-on-top overlay process (macOS Tk)."""

from __future__ import annotations

import json
import math
import os
import select
import socket
import sys
import tkinter as tk
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ipc import pid_path, socket_path  # noqa: E402
from shapes import scale_xy  # noqa: E402

HEX = {
    "black": "#111111",
    "blue": "#0A84FF",
    "green": "#30D158",
    "orange": "#FF9F0A",
    "purple": "#BF5AF2",
    "red": "#FF3B30",
    "white": "#FFFFFF",
    "yellow": "#FFD60A",
}
HALO = {
    "black": "#FFFFFF",
    "blue": "#001428",
    "green": "#00240C",
    "orange": "#2A1600",
    "purple": "#1A0028",
    "red": "#2A0000",
    "white": "#111111",
    "yellow": "#1A1400",
}


def _macos_clickthrough(root: tk.Tk) -> None:
    """Ask the Tk NSWindow to ignore mouse events and forward them."""
    if sys.platform != "darwin":
        return
    try:
        import ctypes
        import ctypes.util
        from ctypes import c_bool, c_void_p

        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        lib.objc_getClass.restype = c_void_p
        lib.sel_registerName.restype = c_void_p
        lib.objc_msgSend.restype = c_void_p
        lib.objc_msgSend.argtypes = [c_void_p, c_void_p]

        def sel(name: str) -> c_void_p:
            return lib.sel_registerName(name.encode("utf-8"))

        nsapp = lib.objc_msgSend(lib.objc_getClass(b"NSApplication"), sel("sharedApplication"))
        windows = lib.objc_msgSend(nsapp, sel("windows"))
        count_fn = lib.objc_msgSend
        count_fn.restype = ctypes.c_ulong
        count = int(count_fn(windows, sel("count")) or 0)
        lib.objc_msgSend.restype = c_void_p
        objectAt = lib.objc_msgSend
        for i in range(count):
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p, ctypes.c_ulong]
            win = lib.objc_msgSend(windows, sel("objectAtIndex:"), i)
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p]
            title = lib.objc_msgSend(win, sel("title"))
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p, c_bool]
            lib.objc_msgSend.restype = c_void_p
            lib.objc_msgSend(win, sel("setIgnoresMouseEvents:"), True)
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p]
            # Keep the title lookup from crashing the loop if a window has none.
            _ = title
    except Exception:
        pass


class OverlayApp:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Hermes HUD Teach")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        if sys.platform == "darwin":
            try:
                self.root.wm_attributes("-transparent", True)
                self.root.config(bg="systemTransparent")
            except tk.TclError:
                self.root.attributes("-alpha", 0.99)
                self.root.config(bg="black")
        else:
            self.root.attributes("-alpha", 0.01)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        if sys.platform == "darwin":
            try:
                self.canvas.config(bg="systemTransparent")
            except tk.TclError:
                self.canvas.config(bg="black")
        self.canvas.pack(fill="both", expand=True)
        self._ttl_job: Optional[str] = None
        self._server = self._bind()
        self.root.after(50, self._poll)
        self.root.after(200, lambda: _macos_clickthrough(self.root))
        self.root.withdraw()

    def _bind(self) -> socket.socket:
        path = socket_path()
        if path.exists():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        server.listen(4)
        server.setblocking(False)
        pid_path().write_text(str(os.getpid()), encoding="utf-8")
        return server

    def _poll(self) -> None:
        try:
            ready, _, _ = select.select([self._server], [], [], 0)
            if ready:
                conn, _ = self._server.accept()
                self._handle(conn)
        except Exception:
            pass
        self.root.after(40, self._poll)

    def _handle(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(1.0)
            raw = b""
            while not raw.endswith(b"\n"):
                chunk = conn.recv(8192)
                if not chunk:
                    break
                raw += chunk
            payload = json.loads(raw.decode("utf-8") or "{}")
            reply = self._dispatch(payload)
            conn.sendall((json.dumps(reply) + "\n").encode("utf-8"))
        except Exception as exc:
            try:
                conn.sendall((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode("utf-8"))
            except OSError:
                pass
        finally:
            conn.close()

    def _dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        op = str(payload.get("op") or "")
        if op == "ping":
            return {"ok": True, "op": "ping"}
        if op == "clear":
            self._clear()
            return {"ok": True, "cleared": True}
        if op == "draw":
            self._draw(payload)
            return {"ok": True, "drawn": len(payload.get("shapes") or [])}
        return {"ok": False, "error": f"unknown op {op!r}"}

    def _clear(self) -> None:
        if self._ttl_job is not None:
            try:
                self.root.after_cancel(self._ttl_job)
            except Exception:
                pass
            self._ttl_job = None
        self.canvas.delete("all")
        self.root.withdraw()

    def _draw(self, payload: dict[str, Any]) -> None:
        bounds = payload.get("bounds") or {}
        x = int(bounds.get("x") or 0)
        y = int(bounds.get("y") or 0)
        w = int(bounds.get("width") or self.root.winfo_screenwidth())
        h = int(bounds.get("height") or self.root.winfo_screenheight())
        if w <= 0 or h <= 0:
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
        fw = float(payload.get("frame_width") or w)
        fh = float(payload.get("frame_height") or h)
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.lift()
        self.root.update_idletasks()
        _macos_clickthrough(self.root)
        self.canvas.delete("all")
        for shape in payload.get("shapes") or []:
            if isinstance(shape, dict):
                self._paint(shape, fw, fh, w, h)
        ttl = float(payload.get("ttl_seconds") or 180)
        if self._ttl_job is not None:
            try:
                self.root.after_cancel(self._ttl_job)
            except Exception:
                pass
        self._ttl_job = self.root.after(max(1, int(ttl * 1000)), self._clear)

    def _xy(self, x: float, y: float, fw: float, fh: float, ow: float, oh: float) -> tuple[float, float]:
        return scale_xy(x, y, fw, fh, ow, oh)

    def _paint(self, shape: dict[str, Any], fw: float, fh: float, ow: float, oh: float) -> None:
        color = HEX.get(str(shape.get("color") or "red"), HEX["red"])
        halo = HALO.get(str(shape.get("color") or "red"), HALO["red"])
        kind = shape.get("kind")
        dashed = bool(shape.get("dashed"))
        dash = (8, 6) if dashed else None
        if kind == "circle":
            cx, cy = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            r = float(shape["radius"]) * (ow / fw if fw else 1)
            self._oval(cx, cy, r, color, halo, dash)
            self._badge(shape, cx - r, cy - r, color)
        elif kind == "rect":
            x, y = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            w = float(shape["width"]) * (ow / fw if fw else 1)
            h = float(shape["height"]) * (oh / fh if fh else 1)
            if shape.get("fill"):
                self.canvas.create_rectangle(x, y, x + w, y + h, fill=halo, outline="")
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=halo, width=6, dash=dash)
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=3, dash=dash)
            self._badge(shape, x, y, color)
        elif kind in ("arrow", "line"):
            x1, y1 = self._xy(float(shape["fromX"]), float(shape["fromY"]), fw, fh, ow, oh)
            x2, y2 = self._xy(float(shape["toX"]), float(shape["toY"]), fw, fh, ow, oh)
            self.canvas.create_line(x1, y1, x2, y2, fill=halo, width=8, dash=dash, capstyle=tk.ROUND)
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=4, dash=dash, capstyle=tk.ROUND)
            if kind == "arrow":
                self._arrow_head(x1, y1, x2, y2, color, halo)
            self._badge(shape, x2, y2, color)
        elif kind == "polyline":
            pts = []
            for p in shape.get("points") or []:
                px, py = self._xy(float(p["x"]), float(p["y"]), fw, fh, ow, oh)
                pts.extend([px, py])
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=halo, width=8, dash=dash, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self.canvas.create_line(*pts, fill=color, width=4, dash=dash, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self._badge(shape, pts[0], pts[1], color)
        elif kind == "label":
            x, y = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            text = str(shape.get("text") or "")
            self.canvas.create_text(x + 1, y + 1, text=text, fill=halo, anchor="nw", font=("Helvetica", 16, "bold"))
            self.canvas.create_text(x, y, text=text, fill=color, anchor="nw", font=("Helvetica", 16, "bold"))
            self._badge(shape, x, y, color)

    def _oval(self, cx: float, cy: float, r: float, color: str, halo: str, dash: Optional[tuple[int, int]]) -> None:
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=halo, width=6, dash=dash)
        self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=3, dash=dash)

    def _arrow_head(self, x1: float, y1: float, x2: float, y2: float, color: str, halo: str) -> None:
        angle = math.atan2(y2 - y1, x2 - x1)
        size = 14
        left = (x2 - size * math.cos(angle - 0.45), y2 - size * math.sin(angle - 0.45))
        right = (x2 - size * math.cos(angle + 0.45), y2 - size * math.sin(angle + 0.45))
        self.canvas.create_polygon(x2, y2, left[0], left[1], right[0], right[1], fill=halo, outline="")
        self.canvas.create_polygon(x2, y2, left[0], left[1], right[0], right[1], fill=color, outline="")

    def _badge(self, shape: dict[str, Any], x: float, y: float, color: str) -> None:
        step = shape.get("step")
        if not isinstance(step, int) or step < 1:
            return
        r = 12
        ink = "#111111" if color in ("#FFD60A", "#FFFFFF") else "#FFFFFF"
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="#111111", width=2)
        self.canvas.create_text(x, y, text=str(step), fill=ink, font=("Helvetica", 12, "bold"))

    def run(self) -> None:
        try:
            self.root.mainloop()
        finally:
            try:
                self._server.close()
            except OSError:
                pass
            for path in (socket_path(), pid_path()):
                try:
                    path.unlink()
                except OSError:
                    pass


def main() -> None:
    OverlayApp().run()


if __name__ == "__main__":
    main()
