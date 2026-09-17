"""Shape validation and coordinate mapping tests (stdlib unittest)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapes import scale_xy, validate_draw_payload, validate_shape
from capture import pick_window
from teach import handle_teach_screen


class ShapeTests(unittest.TestCase):
    def test_circle_ok(self) -> None:
        self.assertIsNone(validate_shape(0, {"kind": "circle", "x": 10, "y": 20, "radius": 8, "step": 1}))

    def test_step_too_high(self) -> None:
        err = validate_shape(0, {"kind": "circle", "x": 1, "y": 1, "radius": 2, "step": 13})
        self.assertIsNotNone(err)
        self.assertIn("step", err or "")

    def test_polyline_needs_two_points(self) -> None:
        err = validate_shape(0, {"kind": "polyline", "points": [{"x": 1, "y": 1}]})
        self.assertIsNotNone(err)

    def test_draw_needs_frame(self) -> None:
        err = validate_draw_payload([{"kind": "circle", "x": 1, "y": 1, "radius": 2}], None, None)
        self.assertIsNotNone(err)

    def test_scale_retina(self) -> None:
        x, y = scale_xy(200, 100, 1600, 800, 800, 400)
        self.assertEqual((x, y), (100.0, 50.0))


class PickWindowTests(unittest.TestCase):
    def test_target_substring(self) -> None:
        windows = [
            {"app": "Finder", "title": "Macintosh HD", "width": 100, "height": 100},
            {"app": "Adobe Photoshop 2025", "title": "Untitled-1", "width": 50, "height": 50},
        ]
        chosen = pick_window(windows, "photoshop")
        self.assertEqual(chosen["app"], "Adobe Photoshop 2025")

    def test_largest_without_target(self) -> None:
        windows = [
            {"app": "A", "title": "", "width": 10, "height": 10},
            {"app": "B", "title": "", "width": 40, "height": 40},
        ]
        chosen = pick_window(windows, None)
        self.assertEqual(chosen["app"], "B")


class TeachDispatchTests(unittest.TestCase):
    def test_unknown_action(self) -> None:
        import json

        raw = handle_teach_screen(action="explode")
        data = json.loads(raw)
        self.assertFalse(data["ok"])
        self.assertIn("action", data["error"])

    def test_draw_rejects_empty_shapes(self) -> None:
        import json

        raw = handle_teach_screen(
            action="draw",
            shapes=[],
            frame_width=100,
            frame_height=100,
            bounds={"x": 0, "y": 0, "width": 100, "height": 100},
        )
        data = json.loads(raw)
        self.assertFalse(data["ok"])


if __name__ == "__main__":
    unittest.main()
