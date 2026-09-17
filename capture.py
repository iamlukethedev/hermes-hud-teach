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
        raise RuntimeError(
            "Could not list windows. Grant Accessibility to Hermes Desktop "
            f"(or the terminal running Hermes) in System Settings. {proc.stderr.strip()}"
        )
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    data = json.loads(raw)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def pick_window(windows: list[dict[str, Any]], target: Optional[str]) -> Optional[dict[str, Any]]:
    """Pick the best window: substring match on app/title, else the largest."""
    if not windows:
        return None
    needle = (target or "").strip().lower()
    if needle:
        hits = [
            w for w in windows
            if needle in str(w.get("app", "")).lower() or needle in str(w.get("title", "")).lower()
        ]
        if hits:
            windows = hits
    return max(windows, key=lambda w: float(w.get("width", 0)) * float(w.get("height", 0)))


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


def capture_region(x: int, y: int, width: int, height: int, dest: Path) -> tuple[int, int]:
    """Screenshot a DIP rectangle and shrink the long edge to 1280px JPEG."""
    png = dest.with_suffix(".png")
    rect = f"{int(x)},{int(y)},{int(width)},{int(height)}"
    shot = _run(["screencapture", "-x", "-R", rect, str(png)], timeout=12)
    if shot.returncode != 0 or not png.is_file() or png.stat().st_size < 32:
        raise RuntimeError(
            "Screenshot failed. Grant Screen Recording to Hermes Desktop in "
            "System Settings → Privacy & Security → Screen Recording. "
            + (shot.stderr or "").strip()
        )
    jpeg = dest.with_suffix(".jpg")
    shrink = _run(["sips", "-Z", "1280", "-s", "format", "jpeg", str(png), "--out", str(jpeg)])
    if shrink.returncode != 0 or not jpeg.is_file():
        raise RuntimeError("Could not compress the screenshot.")
    png.unlink(missing_ok=True)
    dest.write_bytes(jpeg.read_bytes())
    if dest != jpeg:
        jpeg.unlink(missing_ok=True)
    return _sips_dim(dest)


def capture_display(dest: Path) -> tuple[int, int, dict[str, int]]:
    """Full main-display capture when no window list is available."""
    png = dest.with_suffix(".png")
    shot = _run(["screencapture", "-x", "-m", str(png)], timeout=12)
    if shot.returncode != 0 or not png.is_file() or png.stat().st_size < 32:
        raise RuntimeError(
            "Screenshot failed. Grant Screen Recording to Hermes Desktop in "
            "System Settings → Privacy & Security → Screen Recording."
        )
    jpeg = dest.with_suffix(".jpg")
    _run(["sips", "-Z", "1280", "-s", "format", "jpeg", str(png), "--out", str(jpeg)])
    png.unlink(missing_ok=True)
    dest.write_bytes(jpeg.read_bytes())
    if dest != jpeg:
        jpeg.unlink(missing_ok=True)
    width, height = _sips_dim(dest)
    # Overlay uses the full screen in DIP; screencapture -m is the main display.
    return width, height, {"x": 0, "y": 0, "width": 0, "height": 0}


def capture_window(target: Optional[str]) -> dict[str, Any]:
    """Capture one window (or the main display) and return metadata plus JPEG bytes."""
    windows = []
    try:
        windows = list_windows()
    except RuntimeError:
        windows = []
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
        else:
            fw, fh, bounds = capture_display(dest)
            # Fill DIP bounds from the JPEG aspect if System Events was denied.
            if bounds["width"] <= 0:
                bounds = {"x": 0, "y": 0, "width": fw, "height": fh}
            app = "display"
            title = "main display"
        blob = dest.read_bytes()
    finally:
        dest.unlink(missing_ok=True)
    return {
        "app": app,
        "title": title,
        "bounds": bounds,
        "frame_width": fw,
        "frame_height": fh,
        "jpeg": blob,
        "windows": windows,
    }
