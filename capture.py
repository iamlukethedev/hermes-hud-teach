"""macOS window list + screenshot via System Events and screencapture."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

LIST_WINDOWS_JS = r"""
function run() {
  const se = Application("System Events");
  const skip = [
    "hermes", "hermes agent", "loginwindow", "window server",
    "systemuiserver", "notification center", "control center",
    "screenshot", "screencaptureui", "dock"
  ];
  const out = [];
  se.processes.whose({ backgroundOnly: false })().forEach(function (proc) {
    let app = "";
    try { app = String(proc.name()); } catch (e) { return; }
    if (skip.indexOf(app.toLowerCase()) !== -1) return;
    let front = false;
    try { front = Boolean(proc.frontmost()); } catch (e1) { front = false; }
    try {
      proc.windows().forEach(function (win) {
        let title = "";
        try { title = String(win.name() || ""); } catch (e2) { title = ""; }
        if (title === "Hermes HUD Teach") return;
        const pos = win.position();
        const size = win.size();
        if (!pos || !size) return;
        const width = Number(size[0]);
        const height = Number(size[1]);
        if (width < 80 || height < 80) return;
        out.push({
          app: app,
          title: title,
          frontmost: front,
          x: Number(pos[0]),
          y: Number(pos[1]),
          width: width,
          height: height
        });
      });
    } catch (e3) {}
  });
  return JSON.stringify(out);
}
"""

SCREEN_RECORDING_HINT = (
    "Grant Screen Recording to Hermes Desktop (or the terminal running Hermes) in "
    "System Settings → Privacy & Security → Screen Recording, then restart that app."
)
ACCESSIBILITY_HINT = (
    "Grant Accessibility to Hermes Desktop (or the terminal running Hermes) in "
    "System Settings → Privacy & Security → Accessibility."
)


class WindowNotFound(LookupError):
    """A named target matched no visible window."""

    def __init__(self, target: str, windows: list[dict[str, Any]]):
        self.target = target
        self.windows = windows
        names = sorted({str(w.get("app", "")) for w in windows if w.get("app")})
        listing = ", ".join(names[:15]) if names else "none (Accessibility may be missing)"
        super().__init__(f"No visible window matches {target!r}. Visible apps: {listing}.")


def _run(argv: list[str], timeout: int = 8) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def list_windows() -> list[dict[str, Any]]:
    """Visible on-screen windows, excluding Hermes chrome."""
    proc = _run(["osascript", "-l", "JavaScript", "-e", LIST_WINDOWS_JS])
    if proc.returncode != 0:
        raise RuntimeError(f"Could not list windows. {ACCESSIBILITY_HINT} {proc.stderr.strip()}".strip())
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def _area(w: dict[str, Any]) -> float:
    return float(w.get("width", 0)) * float(w.get("height", 0))


def pick_window(windows: list[dict[str, Any]], target: Optional[str]) -> Optional[dict[str, Any]]:
    """Pick a window: substring match on app/title, else the frontmost app's largest, else the largest.

    A named target that matches nothing raises WindowNotFound rather than silently
    teaching on a different app.
    """
    if not windows:
        return None
    needle = (target or "").strip().lower()
    if needle:
        exact = [w for w in windows if str(w.get("app", "")).lower() == needle]
        hits = exact or [
            w for w in windows
            if needle in str(w.get("app", "")).lower() or needle in str(w.get("title", "")).lower()
        ]
        if not hits:
            raise WindowNotFound(target or "", windows)
        return max(hits, key=_area)
    front = [w for w in windows if w.get("frontmost")]
    return max(front or windows, key=_area)


def find_window(windows: list[dict[str, Any]], app: str, title: str) -> Optional[dict[str, Any]]:
    """The window a capture came from, matched by app and title."""
    same_app = [w for w in windows if str(w.get("app", "")) == app]
    same_title = [w for w in same_app if str(w.get("title", "")) == title]
    if same_title:
        return max(same_title, key=_area)
    if len(same_app) == 1:
        return same_app[0]
    return None


def _sips_dim(path: Path) -> tuple[int, int]:
    proc = _run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)])
    width = height = 0
    for line in (proc.stdout or "").splitlines():
        if "pixelWidth:" in line:
            width = int(line.split(":")[-1].strip())
        elif "pixelHeight:" in line:
            height = int(line.split(":")[-1].strip())
    if width <= 0 or height <= 0:
        raise RuntimeError("Could not read screenshot dimensions.")
    return width, height


def _shrink(png: Path, dest: Path) -> tuple[int, int]:
    jpeg = dest.with_suffix(".jpg")
    shrink = _run(["sips", "-Z", "1280", "-s", "format", "jpeg", str(png), "--out", str(jpeg)])
    png.unlink(missing_ok=True)
    if shrink.returncode != 0 or not jpeg.is_file():
        raise RuntimeError("Could not compress the screenshot.")
    if dest != jpeg:
        dest.write_bytes(jpeg.read_bytes())
        jpeg.unlink(missing_ok=True)
    return _sips_dim(dest)


def capture_region(x: int, y: int, width: int, height: int, dest: Path) -> tuple[int, int]:
    """Screenshot a DIP rectangle and shrink the long edge to 1280px JPEG."""
    png = dest.with_suffix(".png")
    rect = f"{int(x)},{int(y)},{int(width)},{int(height)}"
    shot = _run(["screencapture", "-x", "-R", rect, str(png)], timeout=12)
    if shot.returncode != 0 or not png.is_file() or png.stat().st_size < 32:
        raise RuntimeError(f"Screenshot failed. {SCREEN_RECORDING_HINT} {(shot.stderr or '').strip()}".strip())
    return _shrink(png, dest)


def capture_display(dest: Path) -> tuple[int, int]:
    """Full main-display capture when no window list is available."""
    png = dest.with_suffix(".png")
    shot = _run(["screencapture", "-x", "-m", str(png)], timeout=12)
    if shot.returncode != 0 or not png.is_file() or png.stat().st_size < 32:
        raise RuntimeError(f"Screenshot failed. {SCREEN_RECORDING_HINT}")
    return _shrink(png, dest)


def capture_window(target: Optional[str]) -> dict[str, Any]:
    """Capture one window (or the main display) and return metadata plus JPEG bytes."""
    windows: list[dict[str, Any]] = []
    window_error = ""
    try:
        windows = list_windows()
    except RuntimeError as exc:
        window_error = str(exc)
    if target and target.strip() and not windows and window_error:
        raise RuntimeError(f"Cannot find {target!r} without the window list. {window_error}")
    chosen = pick_window(windows, target)
    dest = Path(tempfile.mkstemp(prefix="hud-teach-", suffix=".jpg")[1])
    try:
        if chosen:
            fw, fh = capture_region(
                int(chosen["x"]),
                int(chosen["y"]),
                int(chosen["width"]),
                int(chosen["height"]),
                dest,
            )
            bounds = {
                "x": int(chosen["x"]),
                "y": int(chosen["y"]),
                "width": int(chosen["width"]),
                "height": int(chosen["height"]),
            }
            app = str(chosen.get("app") or "")
            title = str(chosen.get("title") or "")
            display = False
        else:
            fw, fh = capture_display(dest)
            # Zero size tells the overlay to cover the whole main display in its own
            # DIP units; the JPEG is shrunk, so its pixel size is not the screen size.
            bounds = {"x": 0, "y": 0, "width": 0, "height": 0}
            app = "display"
            title = "main display"
            display = True
        blob = dest.read_bytes()
    finally:
        dest.unlink(missing_ok=True)
    return {
        "app": app,
        "title": title,
        "bounds": bounds,
        "frame_width": fw,
        "frame_height": fh,
        "display": display,
        "jpeg": blob,
        "windows": windows,
        "window_error": window_error,
    }


def check_permissions() -> dict[str, Any]:
    """Probe Accessibility (window list) and Screen Recording (a 1x1 capture)."""
    report: dict[str, Any] = {}
    try:
        windows = list_windows()
        report["accessibility"] = {"ok": True, "windows": len(windows)}
    except Exception as exc:
        report["accessibility"] = {"ok": False, "fix": ACCESSIBILITY_HINT, "detail": str(exc)[:300]}
    probe = Path(tempfile.mkstemp(prefix="hud-teach-check-", suffix=".png")[1])
    try:
        shot = _run(["screencapture", "-x", "-R", "0,0,1,1", str(probe)], timeout=8)
        ok = shot.returncode == 0 and probe.is_file() and probe.stat().st_size >= 32
        report["screen_recording"] = (
            {"ok": True}
            if ok
            else {"ok": False, "fix": SCREEN_RECORDING_HINT, "detail": (shot.stderr or "").strip()[:300]}
        )
    except Exception as exc:
        report["screen_recording"] = {"ok": False, "fix": SCREEN_RECORDING_HINT, "detail": str(exc)[:300]}
    finally:
        probe.unlink(missing_ok=True)
    return report
