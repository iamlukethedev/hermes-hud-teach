"""End-to-end overlay daemon test: spawn it, draw a lesson over the socket, read back state.

Needs Tk and a display (macOS, or Linux under xvfb-run). Skipped otherwise.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import overlay  # noqa: E402

HAS_TK = importlib.util.find_spec("tkinter") is not None
HAS_DISPLAY = sys.platform == "darwin" or bool(os.environ.get("DISPLAY"))

SHAPES = [
    {"kind": "rect", "x": 40, "y": 40, "width": 200, "height": 80, "step": 1, "color": "blue", "label": "File menu"},
    {"kind": "circle", "x": 400, "y": 300, "radius": 30, "step": 2, "color": "yellow"},
    {"kind": "arrow", "fromX": 100, "fromY": 500, "toX": 380, "toY": 320, "step": 3},
    {"kind": "label", "x": 500, "y": 500, "text": "then Export", "step": 4, "color": "green"},
    {"kind": "polyline", "points": [{"x": 10, "y": 10}, {"x": 50, "y": 60}, {"x": 90, "y": 10}], "dashed": True},
]
STEPS = [
    {"n": 1, "text": "Open the File menu", "done": True},
    {"n": 2, "text": "Click Export As…", "done": False},
    {"n": 3, "text": "Pick PNG and save", "done": False},
]


@unittest.skipUnless(HAS_TK and HAS_DISPLAY, "needs tkinter and a display (use xvfb-run on Linux)")
class OverlayDaemonTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"HUD_TEACH_HOME": self._tmp.name})
        self._env.start()

    def tearDown(self) -> None:
        try:
            overlay.stop()
            deadline = time.time() + 3
            while time.time() < deadline and overlay.status().get("running"):
                time.sleep(0.05)
        finally:
            self._env.stop()
            self._tmp.cleanup()

    def draw(self, **extra):
        args = dict(
            bounds={"x": 0, "y": 0, "width": 640, "height": 400},
            frame_width=1280.0,
            frame_height=800.0,
            shapes=SHAPES,
            ttl_seconds=30,
        )
        args.update(extra)
        return overlay.draw(**args)

    def test_lesson_round_trip(self) -> None:
        self.assertFalse(overlay.status()["running"])
        reply = self.draw(title="Export a PNG", steps=STEPS, current_step=2, legend_position="auto")
        self.assertTrue(reply["ok"], reply)
        self.assertEqual(reply["drawn"], len(SHAPES))

        state = overlay.status()
        self.assertTrue(state["running"])
        self.assertTrue(state["visible"])
        self.assertEqual(state["shapes"], len(SHAPES))
        self.assertEqual(state["title"], "Export a PNG")
        self.assertEqual(state["steps"], 3)
        self.assertEqual(state["current_step"], 2)
        self.assertEqual(state["pulsing"], 1)
        self.assertIn(state["legend"], ("top-left", "top-right", "bottom-left", "bottom-right"))
        self.assertGreater(state["canvas_items"], 20)
        self.assertGreater(state["expires_in"], 20)

        cleared = overlay.clear()
        self.assertTrue(cleared["cleared"])
        after = overlay.status()
        self.assertFalse(after["visible"])
        self.assertEqual(after["canvas_items"], 0)
        self.assertEqual(after["pulsing"], 0)

    def test_marks_only_and_ttl_expiry(self) -> None:
        reply = self.draw(ttl_seconds=0.6)
        self.assertTrue(reply["ok"], reply)
        state = overlay.status()
        self.assertTrue(state["visible"])
        self.assertIsNone(state["legend"])
        self.assertEqual(state["pulsing"], 0)
        deadline = time.time() + 4
        while time.time() < deadline and overlay.status().get("visible"):
            time.sleep(0.1)
        self.assertFalse(overlay.status()["visible"])

    def test_new_draw_replaces_previous(self) -> None:
        self.draw(title="First", steps=STEPS, current_step=1)
        first = overlay.status()["canvas_items"]
        self.draw(shapes=SHAPES[:1])
        state = overlay.status()
        self.assertEqual(state["shapes"], 1)
        self.assertIsNone(state["title"])
        self.assertLess(state["canvas_items"], first)

    def test_idle_daemon_exits(self) -> None:
        with mock.patch.dict(os.environ, {"HUD_TEACH_IDLE_EXIT": "1"}):
            self.assertTrue(self.draw()["ok"])
        self.assertTrue(overlay.clear()["cleared"])
        deadline = time.time() + 5
        while time.time() < deadline and overlay.status().get("running"):
            time.sleep(0.1)
        self.assertFalse(overlay.status()["running"])

    def test_full_display_bounds(self) -> None:
        reply = self.draw(bounds={"x": 0, "y": 0, "width": 0, "height": 0})
        self.assertTrue(reply["ok"], reply)
        bounds = overlay.status()["bounds"]
        self.assertGreater(bounds["width"], 0)
        self.assertGreater(bounds["height"], 0)


if __name__ == "__main__":
    unittest.main()
