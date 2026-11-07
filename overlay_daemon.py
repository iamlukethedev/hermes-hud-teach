#!/usr/bin/env python3
"""Click-through always-on-top overlay process (macOS Tk)."""

from __future__ import annotations

import json
import math
import os
import select
import socket
import sys
import time
import tkinter as tk
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ipc import pid_path, socket_path  # noqa: E402
from shapes import pick_legend_corner, scale_xy  # noqa: E402

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
CARD_BG = "#1C1C1E"
CARD_EDGE = "#3A3A3C"
CARD_TEXT = "#F2F2F7"
CARD_MUTED = "#8E8E93"
CURRENT = "#FFD60A"
FONT = "Helvetica"
PULSE_MS = 60
IDLE_EXIT_SECONDS = float(os.environ.get("HUD_TEACH_IDLE_EXIT", "1800"))


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
        lib.objc_msgSend.restype = ctypes.c_ulong
        count = int(lib.objc_msgSend(windows, sel("count")) or 0)
        lib.objc_msgSend.restype = c_void_p
        for i in range(count):
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p, ctypes.c_ulong]
            win = lib.objc_msgSend(windows, sel("objectAtIndex:"), i)
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p, c_bool]
            lib.objc_msgSend(win, sel("setIgnoresMouseEvents:"), True)
            lib.objc_msgSend.argtypes = [c_void_p, c_void_p]
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
            # No per-pixel transparency off macOS; HUD_TEACH_OPAQUE renders a visible
            # preview for tests and docs.
            if not os.environ.get("HUD_TEACH_OPAQUE"):
                self.root.attributes("-alpha", 0.01)
        self.canvas = tk.Canvas(self.root, highlightthickness=0, bd=0)
        if sys.platform == "darwin":
            try:
                self.canvas.config(bg="systemTransparent")
            except tk.TclError:
                self.canvas.config(bg="black")
        self.canvas.pack(fill="both", expand=True)
        self._ttl_job: Optional[str] = None
        self._pulse_job: Optional[str] = None
        self._pulse_anchors: list[tuple[float, float, str]] = []
        self._pulse_phase = 0
        self._idle_job: Optional[str] = None
        self._state: dict[str, Any] = {"visible": False}
        self._server = self._bind()
        self.root.after(50, self._poll)
        self.root.after(200, lambda: _macos_clickthrough(self.root))
        self.root.withdraw()
        self._arm_idle_exit()

    def _arm_idle_exit(self) -> None:
        """Quit after a long stretch with nothing on screen; the next draw restarts the daemon."""
        self._cancel(self._idle_job)
        self._idle_job = None
        if IDLE_EXIT_SECONDS > 0:
            self._idle_job = self.root.after(int(IDLE_EXIT_SECONDS * 1000), self.root.destroy)

    def _bind(self) -> socket.socket:
        path = socket_path()
        if path.exists():
            path.unlink()
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(str(path))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
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
            return {"ok": True, "op": "ping", "pid": os.getpid()}
        if op == "status":
            return {"ok": True, **self._status()}
        if op == "clear":
            self._clear()
            return {"ok": True, "cleared": True}
        if op == "draw":
            self._draw(payload)
            return {"ok": True, "drawn": len(payload.get("shapes") or []), **self._status()}
        if op == "quit":
            self.root.after(50, self.root.destroy)
            return {"ok": True, "stopped": True}
        return {"ok": False, "error": f"unknown op {op!r}"}

    def _status(self) -> dict[str, Any]:
        state = dict(self._state)
        expires = state.pop("expires_at", None)
        if state.get("visible") and expires:
            state["expires_in"] = max(0, int(round(expires - time.time())))
        state["canvas_items"] = len(self.canvas.find_all())
        state["pulsing"] = len(self._pulse_anchors)
        return state

    def _cancel(self, job: Optional[str]) -> None:
        if job is not None:
            try:
                self.root.after_cancel(job)
            except Exception:
                pass

    def _clear(self) -> None:
        self._cancel(self._ttl_job)
        self._ttl_job = None
        self._cancel(self._pulse_job)
        self._pulse_job = None
        self._pulse_anchors = []
        self.canvas.delete("all")
        self.root.withdraw()
        self._state = {"visible": False}
        self._arm_idle_exit()

    def _draw(self, payload: dict[str, Any]) -> None:
        bounds = payload.get("bounds") or {}
        x = int(bounds.get("x") or 0)
        y = int(bounds.get("y") or 0)
        w = int(bounds.get("width") or 0)
        h = int(bounds.get("height") or 0)
        if w <= 0 or h <= 0:
            x, y = 0, 0
            w = self.root.winfo_screenwidth()
            h = self.root.winfo_screenheight()
        fw = float(payload.get("frame_width") or w)
        fh = float(payload.get("frame_height") or h)
        self._cancel(self._idle_job)
        self._idle_job = None
        self._cancel(self._pulse_job)
        self._pulse_job = None
        self._pulse_anchors = []
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.deiconify()
        self.root.lift()
        self.root.update_idletasks()
        _macos_clickthrough(self.root)
        self.canvas.delete("all")
        shapes = [s for s in payload.get("shapes") or [] if isinstance(s, dict)]
        current = payload.get("current_step")
        current = current if isinstance(current, int) and not isinstance(current, bool) else None
        for shape in shapes:
            self._paint(shape, fw, fh, w, h, current)
        steps = [s for s in payload.get("steps") or [] if isinstance(s, dict)]
        title = payload.get("title") if isinstance(payload.get("title"), str) else None
        legend = None
        if steps or title:
            legend = pick_legend_corner(shapes, fw, fh, str(payload.get("legend_position") or "auto"))
            self._legend(title, steps, current, legend, w, h)
        if self._pulse_anchors:
            self._pulse()
        ttl = float(payload.get("ttl_seconds") or 180)
        self._cancel(self._ttl_job)
        self._ttl_job = self.root.after(max(1, int(ttl * 1000)), self._clear)
        self._state = {
            "visible": True,
            "shapes": len(shapes),
            "title": title,
            "steps": len(steps),
            "current_step": current,
            "legend": legend,
            "bounds": {"x": x, "y": y, "width": w, "height": h},
            "expires_at": time.time() + ttl,
        }

    def _xy(self, x: float, y: float, fw: float, fh: float, ow: float, oh: float) -> tuple[float, float]:
        return scale_xy(x, y, fw, fh, ow, oh)

    def _paint(self, shape: dict[str, Any], fw: float, fh: float, ow: float, oh: float, current: Optional[int]) -> None:
        color = HEX.get(str(shape.get("color") or "red"), HEX["red"])
        halo = HALO.get(str(shape.get("color") or "red"), HALO["red"])
        kind = shape.get("kind")
        dash = (8, 6) if shape.get("dashed") else None
        anchor: Optional[tuple[float, float]] = None
        caption_at: Optional[tuple[float, float, str]] = None
        if kind == "circle":
            cx, cy = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            r = float(shape["radius"]) * (ow / fw if fw else 1)
            self._oval(cx, cy, r, color, halo, dash)
            anchor = (cx - r * 0.7071, cy - r * 0.7071)
            caption_at = (cx + r + 8, cy, "w")
        elif kind == "rect":
            x, y = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            w = float(shape["width"]) * (ow / fw if fw else 1)
            h = float(shape["height"]) * (oh / fh if fh else 1)
            if shape.get("fill"):
                self.canvas.create_rectangle(x, y, x + w, y + h, fill=halo, outline="")
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=halo, width=6, dash=dash)
            self.canvas.create_rectangle(x, y, x + w, y + h, outline=color, width=3, dash=dash)
            anchor = (x, y)
            # Captions sit outside the outline so the border never strikes through them.
            caption_at = (x + 16, y - 6, "sw") if y > 24 else (x + 2, y + h + 6, "nw")
        elif kind in ("arrow", "line"):
            x1, y1 = self._xy(float(shape["fromX"]), float(shape["fromY"]), fw, fh, ow, oh)
            x2, y2 = self._xy(float(shape["toX"]), float(shape["toY"]), fw, fh, ow, oh)
            self.canvas.create_line(x1, y1, x2, y2, fill=halo, width=8, dash=dash, capstyle=tk.ROUND)
            self.canvas.create_line(x1, y1, x2, y2, fill=color, width=4, dash=dash, capstyle=tk.ROUND)
            if kind == "arrow":
                self._arrow_head(x1, y1, x2, y2, color, halo)
            # Badge the tail so it never sits on top of the control the arrow points at.
            anchor = (x1, y1) if kind == "arrow" else (x2, y2)
        elif kind == "polyline":
            pts: list[float] = []
            for p in shape.get("points") or []:
                px, py = self._xy(float(p["x"]), float(p["y"]), fw, fh, ow, oh)
                pts.extend([px, py])
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=halo, width=8, dash=dash, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self.canvas.create_line(*pts, fill=color, width=4, dash=dash, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                anchor = (pts[0], pts[1])
        elif kind == "label":
            x, y = self._xy(float(shape["x"]), float(shape["y"]), fw, fh, ow, oh)
            text = str(shape.get("text") or "")
            self._halo_text(x + 16 if shape.get("step") else x, y, text, color, halo, 16, "w" if shape.get("step") else "nw")
            anchor = (x, y)
        if anchor is None:
            return
        step = shape.get("step")
        has_badge = isinstance(step, int) and not isinstance(step, bool) and step >= 1
        if has_badge:
            self._badge(step, anchor[0], anchor[1], color)
            if current is not None and step == current:
                self._pulse_anchors.append((anchor[0], anchor[1], color))
        label = shape.get("label")
        if kind != "label" and isinstance(label, str) and label.strip():
            lx, ly, where = caption_at or (anchor[0] + (18 if has_badge else 0), anchor[1], "w")
            self._halo_text(lx, ly, label.strip(), color, halo, 14, where)

    def _halo_text(self, x: float, y: float, text: str, color: str, halo: str, size: int, anchor: str) -> None:
        font = (FONT, size, "bold")
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (1, 1)):
            self.canvas.create_text(x + dx, y + dy, text=text, fill=halo, anchor=anchor, font=font)
        self.canvas.create_text(x, y, text=text, fill=color, anchor=anchor, font=font)

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

    def _badge(self, step: int, x: float, y: float, color: str) -> None:
        r = 12
        ink = "#111111" if color in ("#FFD60A", "#FFFFFF") else "#FFFFFF"
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=color, outline="#111111", width=2, tags=("badge",))
        self.canvas.create_text(x, y, text=str(step), fill=ink, font=(FONT, 12, "bold"), tags=("badge",))

    def _pulse(self) -> None:
        """Breathing ring around the current step's badge so the eye finds it first."""
        self.canvas.delete("pulse")
        wave = (math.sin(self._pulse_phase / 4.0) + 1) / 2
        radius = 15 + 9 * wave
        for x, y, color in self._pulse_anchors:
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, outline=color, width=3, tags=("pulse",))
        self.canvas.tag_lower("pulse", "badge")
        self._pulse_phase += 1
        self._pulse_job = self.root.after(PULSE_MS, self._pulse)

    def _legend(
        self,
        title: Optional[str],
        steps: list[dict[str, Any]],
        current: Optional[int],
        corner: str,
        ow: float,
        oh: float,
    ) -> None:
        """Step card: lesson title, numbered instructions, done/current state."""
        pad, gap, margin = 12, 6, 14
        card_w = int(min(360, max(220, ow * 0.42)))
        text_w = card_w - pad * 2 - 30
        tag = "legend"
        y = pad
        if title:
            item = self.canvas.create_text(
                pad, y, text=title, fill=CARD_TEXT, anchor="nw", width=card_w - pad * 2,
                font=(FONT, 14, "bold"), tags=(tag,),
            )
            y = self.canvas.bbox(item)[3] + gap + 2
        for index, step in enumerate(steps, start=1):
            n = step.get("n") if isinstance(step.get("n"), int) and step.get("n") > 0 else index
            done = bool(step.get("done"))
            is_current = current is not None and n == current
            fill = CURRENT if is_current else (CARD_MUTED if done else HEX["blue"])
            ink = "#111111" if is_current else "#FFFFFF"
            text_color = CARD_MUTED if done and not is_current else CARD_TEXT
            item = self.canvas.create_text(
                pad + 30, y, text=str(step.get("text") or ""), fill=text_color, anchor="nw", width=text_w,
                font=(FONT, 12, "bold" if is_current else "normal"), tags=(tag,),
            )
            top, bottom = self.canvas.bbox(item)[1], self.canvas.bbox(item)[3]
            cy = top + 9
            self.canvas.create_oval(pad + 2, cy - 9, pad + 20, cy + 9, fill=fill, outline="", tags=(tag,))
            self.canvas.create_text(
                pad + 11, cy, text="✓" if done and not is_current else str(n), fill=ink,
                font=(FONT, 10, "bold"), tags=(tag,),
            )
            y = max(bottom, cy + 9) + gap
        if current is not None and steps:
            self.canvas.create_text(
                pad, y + 2, text=f"Step {current} of {len(steps)}", fill=CARD_MUTED, anchor="nw",
                font=(FONT, 11, "normal"), tags=(tag,),
            )
            y += 18
        card_h = y + pad - gap
        first = self.canvas.find_withtag(tag)
        bg = self.canvas.create_rectangle(0, 0, card_w, card_h, fill=CARD_BG, outline=CARD_EDGE, width=1, tags=(tag,))
        accent = self.canvas.create_rectangle(0, 0, 4, card_h, fill=CURRENT, outline="", tags=(tag,))
        if first:
            self.canvas.tag_lower(accent, first[0])
            self.canvas.tag_lower(bg, accent)
        left = margin if corner.endswith("left") else ow - card_w - margin
        top = margin if corner.startswith("top") else oh - card_h - margin
        self.canvas.move(tag, max(0, left), max(0, top))

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
