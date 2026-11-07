"""Shape, lesson validation and coordinate mapping tests (stdlib unittest)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shapes import (  # noqa: E402
    check_in_frame,
    normalize_steps,
    pick_legend_corner,
    scale_xy,
    validate_draw_payload,
    validate_lesson,
    validate_shape,
)


class ShapeTests(unittest.TestCase):
    def test_circle_ok(self) -> None:
        self.assertIsNone(validate_shape(0, {"kind": "circle", "x": 10, "y": 20, "radius": 8, "step": 1}))

    def test_step_too_high(self) -> None:
        err = validate_shape(0, {"kind": "circle", "x": 1, "y": 1, "radius": 2, "step": 13})
        self.assertIn("step", err or "")

    def test_bool_is_not_a_step(self) -> None:
        self.assertIsNotNone(validate_shape(0, {"kind": "circle", "x": 1, "y": 1, "radius": 2, "step": True}))

    def test_polyline_needs_two_points(self) -> None:
        self.assertIsNotNone(validate_shape(0, {"kind": "polyline", "points": [{"x": 1, "y": 1}]}))

    def test_label_needs_text(self) -> None:
        self.assertIsNotNone(validate_shape(0, {"kind": "label", "x": 1, "y": 1, "text": "  "}))

    def test_unknown_color(self) -> None:
        err = validate_shape(0, {"kind": "rect", "x": 1, "y": 1, "width": 2, "height": 2, "color": "pink"})
        self.assertIn("color", err or "")

    def test_draw_needs_frame(self) -> None:
        self.assertIsNotNone(validate_draw_payload([{"kind": "circle", "x": 1, "y": 1, "radius": 2}], None, None))

    def test_draw_caps_shape_count(self) -> None:
        shapes = [{"kind": "circle", "x": 1, "y": 1, "radius": 1}] * 25
        self.assertIn("capped", validate_draw_payload(shapes, 100, 100) or "")

    def test_scale_retina(self) -> None:
        self.assertEqual(scale_xy(200, 100, 1600, 800, 800, 400), (100.0, 50.0))


class FrameBoundsTests(unittest.TestCase):
    def test_inside_frame_passes(self) -> None:
        shapes = [{"kind": "arrow", "fromX": 0, "fromY": 0, "toX": 1280, "toY": 800}]
        self.assertIsNone(check_in_frame(shapes, 1280, 800))

    def test_small_overhang_is_allowed(self) -> None:
        shapes = [{"kind": "circle", "x": 5, "y": 5, "radius": 20}]
        self.assertIsNone(check_in_frame(shapes, 1280, 800))

    def test_far_outside_is_rejected(self) -> None:
        shapes = [{"kind": "rect", "x": 100, "y": 100, "width": 2000, "height": 20}]
        err = validate_draw_payload(shapes, 1280, 800)
        self.assertIn("outside", err or "")
        self.assertIn("shapes[0]", err or "")

    def test_polyline_point_outside(self) -> None:
        shapes = [{"kind": "polyline", "points": [{"x": 1, "y": 1}, {"x": 1, "y": 5000}]}]
        self.assertIsNotNone(check_in_frame(shapes, 1280, 800))


class LessonTests(unittest.TestCase):
    def test_strings_and_objects(self) -> None:
        steps = ["Open File", {"text": "Choose Export", "done": True}]
        self.assertIsNone(validate_lesson("Export a PNG", steps, 2, "auto"))
        self.assertEqual(
            normalize_steps(steps),
            [{"n": 1, "text": "Open File", "done": False}, {"n": 2, "text": "Choose Export", "done": True}],
        )

    def test_current_step_past_end(self) -> None:
        self.assertIn("past", validate_lesson(None, ["a", "b"], 3, None) or "")

    def test_current_step_without_steps_is_allowed(self) -> None:
        self.assertIsNone(validate_lesson(None, None, 2, None))

    def test_empty_step_text(self) -> None:
        self.assertIsNotNone(validate_lesson(None, [{"text": ""}], None, None))

    def test_done_must_be_bool(self) -> None:
        self.assertIsNotNone(validate_lesson(None, [{"text": "a", "done": "yes"}], None, None))

    def test_too_many_steps(self) -> None:
        self.assertIsNotNone(validate_lesson(None, ["x"] * 13, None, None))

    def test_bad_legend_position(self) -> None:
        self.assertIsNotNone(validate_lesson(None, None, None, "middle"))

    def test_legend_avoids_marks(self) -> None:
        marks_top_right = [{"kind": "circle", "x": 1200, "y": 60, "radius": 20}]
        self.assertEqual(pick_legend_corner(marks_top_right, 1280, 800), "top-left")
        self.assertEqual(pick_legend_corner([], 1280, 800), "top-right")
        self.assertEqual(pick_legend_corner(marks_top_right, 1280, 800, "bottom-left"), "bottom-left")


if __name__ == "__main__":
    unittest.main()
