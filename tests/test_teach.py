"""teach_screen dispatch tests with the macOS edges (screencapture, osascript, Tk) faked."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import capture  # noqa: E402
import last_capture  # noqa: E402
import overlay  # noqa: E402
import teach  # noqa: E402
from capture import WindowNotFound, find_window, pick_window  # noqa: E402

CHESS = {"app": "Chess", "title": "Game 1", "frontmost": False, "x": 100, "y": 80, "width": 640, "height": 400}
FINDER = {"app": "Finder", "title": "Downloads", "frontmost": True, "x": 0, "y": 0, "width": 300, "height": 200}


def fake_shot(window=CHESS, display=False):
    return {
        "app": "display" if display else window["app"],
        "title": "main display" if display else window["title"],
        "bounds": {"x": 0, "y": 0, "width": 0, "height": 0} if display else {
            k: window[k] for k in ("x", "y", "width", "height")
        },
        "frame_width": 1280,
        "frame_height": 800,
        "display": display,
        "jpeg": b"\xff\xd8fakejpeg",
        "windows": [] if display else [window],
        "window_error": "",
    }


class IsolatedHome(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._env = mock.patch.dict(os.environ, {"HUD_TEACH_HOME": self._tmp.name})
        self._env.start()
        self._mac = mock.patch.object(teach, "macos_only", return_value=True)
        self._mac.start()
        self.drawn: list[dict] = []
        self._draw = mock.patch.object(overlay, "draw", side_effect=self._record_draw)
        self._draw.start()

    def tearDown(self) -> None:
        self._draw.stop()
        self._mac.stop()
        self._env.stop()
        self._tmp.cleanup()

    def _record_draw(self, **kwargs):
        self.drawn.append(kwargs)
        return {"ok": True, "drawn": len(kwargs["shapes"]), "title": kwargs.get("title"), "legend": "top-left"}

    def call(self, **kwargs) -> dict:
        raw = teach.handle_teach_screen(**kwargs)
        return raw if isinstance(raw, dict) else json.loads(raw)

    def do_capture(self, window=CHESS, display=False) -> dict:
        with mock.patch.object(capture, "capture_window", return_value=fake_shot(window, display)):
            return self.call(action="capture", target=window["app"])


class DispatchTests(IsolatedHome):
    def test_unknown_action(self) -> None:
        data = self.call(action="explode")
        self.assertFalse(data["ok"])
        self.assertIn("action", data["error"])

    def test_non_macos_refuses_drawing_but_check_runs(self) -> None:
        with mock.patch.object(teach, "macos_only", return_value=False):
            self.assertIn("macOS", self.call(action="capture")["error"])
            report = self.call(action="check")
        self.assertTrue(report["ok"])
        self.assertFalse(report["ready"])
        self.assertIn("macos", report["checks"])
        self.assertTrue(any("macOS" in s for s in report["next_steps"]))

    def test_draw_before_capture_explains(self) -> None:
        data = self.call(action="draw", shapes=[{"kind": "circle", "x": 1, "y": 1, "radius": 2}])
        self.assertFalse(data["ok"])
        self.assertIn("capture", data["error"])

    def test_draw_rejects_empty_shapes(self) -> None:
        data = self.call(
            action="draw", shapes=[], frame_width=100, frame_height=100,
            bounds={"x": 0, "y": 0, "width": 100, "height": 100},
        )
        self.assertFalse(data["ok"])

    def test_capture_returns_image_and_capture_id(self) -> None:
        result = self.do_capture()
        self.assertTrue(result["_multimodal"])
        meta = json.loads(result["content"][0]["text"])
        self.assertEqual(meta["app"], "Chess")
        self.assertTrue(meta["capture_id"])
        self.assertTrue(result["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(last_capture.load_capture()["capture_id"], meta["capture_id"])

    def test_capture_unknown_target_lists_windows(self) -> None:
        err = WindowNotFound("Photoshop", [CHESS, FINDER])
        with mock.patch.object(capture, "capture_window", side_effect=err):
            data = self.call(action="capture", target="Photoshop")
        self.assertFalse(data["ok"])
        self.assertIn("Photoshop", data["error"])
        self.assertEqual({w["app"] for w in data["windows"]}, {"Chess", "Finder"})


class DrawFlowTests(IsolatedHome):
    SHAPES = [{"kind": "circle", "x": 640, "y": 400, "radius": 30, "step": 1, "label": "Knight"}]

    def test_draw_defaults_to_last_capture(self) -> None:
        self.do_capture()
        with mock.patch.object(capture, "list_windows", return_value=[CHESS]):
            data = self.call(action="draw", shapes=self.SHAPES)
        self.assertTrue(data["ok"], data)
        sent = self.drawn[-1]
        self.assertEqual(sent["frame_width"], 1280.0)
        self.assertEqual(sent["bounds"], {"x": 100, "y": 80, "width": 640, "height": 400})
        self.assertNotIn("notes", data)

    def test_moved_window_is_followed(self) -> None:
        self.do_capture()
        moved = {**CHESS, "x": 300, "y": 200}
        with mock.patch.object(capture, "list_windows", return_value=[moved, FINDER]):
            data = self.call(action="draw", shapes=self.SHAPES)
        self.assertTrue(data["ok"], data)
        self.assertEqual(self.drawn[-1]["bounds"]["x"], 300)
        self.assertTrue(any("moved" in n for n in data["notes"]))

    def test_resized_window_is_refused(self) -> None:
        self.do_capture()
        resized = {**CHESS, "width": 900}
        with mock.patch.object(capture, "list_windows", return_value=[resized]):
            data = self.call(action="draw", shapes=self.SHAPES)
        self.assertFalse(data["ok"])
        self.assertIn("resized", data["error"])
        self.assertEqual(self.drawn, [])

    def test_missing_window_draws_with_note(self) -> None:
        self.do_capture()
        with mock.patch.object(capture, "list_windows", return_value=[FINDER]):
            data = self.call(action="draw", shapes=self.SHAPES)
        self.assertTrue(data["ok"])
        self.assertTrue(any("not found" in n for n in data["notes"]))

    def test_display_capture_does_not_follow(self) -> None:
        self.do_capture(display=True)
        with mock.patch.object(capture, "list_windows", side_effect=AssertionError("should not list")):
            data = self.call(action="draw", shapes=self.SHAPES)
        self.assertTrue(data["ok"], data)
        self.assertEqual(self.drawn[-1]["bounds"], {"x": 0, "y": 0, "width": 0, "height": 0})

    def test_stale_capture_id_is_refused(self) -> None:
        self.do_capture()
        data = self.call(action="draw", shapes=self.SHAPES, capture_id="deadbeef")
        self.assertFalse(data["ok"])
        self.assertIn("capture_id", data["error"])

    def test_explicit_geometry_still_works(self) -> None:
        data = self.call(
            action="draw", shapes=self.SHAPES, frame_width=1280, frame_height=800,
            bounds={"x": 5, "y": 6, "width": 640, "height": 400},
        )
        self.assertTrue(data["ok"], data)
        self.assertEqual(self.drawn[-1]["bounds"]["x"], 5)

    def test_out_of_frame_coordinates_are_rejected(self) -> None:
        self.do_capture()
        data = self.call(action="draw", shapes=[{"kind": "circle", "x": 4000, "y": 10, "radius": 5}])
        self.assertFalse(data["ok"])
        self.assertIn("outside", data["error"])

    def test_lesson_is_forwarded(self) -> None:
        self.do_capture()
        with mock.patch.object(capture, "list_windows", return_value=[CHESS]):
            data = self.call(
                action="draw", shapes=self.SHAPES, title="Develop the knight",
                steps=[{"text": "Find the knight", "done": True}, "Move it to f3"], current_step=2,
            )
        self.assertTrue(data["ok"], data)
        sent = self.drawn[-1]
        self.assertEqual(sent["title"], "Develop the knight")
        self.assertEqual(sent["current_step"], 2)
        self.assertEqual([s["done"] for s in sent["steps"]], [True, False])
        self.assertEqual(data["steps"], 2)

    def test_bad_lesson_is_rejected_before_drawing(self) -> None:
        self.do_capture()
        data = self.call(action="draw", shapes=self.SHAPES, steps=["a"], current_step=4)
        self.assertFalse(data["ok"])
        self.assertEqual(self.drawn, [])

    def test_ttl_bounds(self) -> None:
        self.do_capture()
        self.assertFalse(self.call(action="draw", shapes=self.SHAPES, ttl_seconds=0)["ok"])
        self.assertFalse(self.call(action="draw", shapes=self.SHAPES, ttl_seconds="soon")["ok"])

    def test_status_reports_last_capture(self) -> None:
        self.do_capture()
        with mock.patch.object(overlay, "status", return_value={"ok": True, "running": False}):
            data = self.call(action="status")
        self.assertEqual(data["last_capture"]["app"], "Chess")


class PickWindowTests(unittest.TestCase):
    def test_target_substring(self) -> None:
        windows = [
            {"app": "Finder", "title": "Macintosh HD", "width": 100, "height": 100},
            {"app": "Adobe Photoshop 2025", "title": "Untitled-1", "width": 50, "height": 50},
        ]
        self.assertEqual(pick_window(windows, "photoshop")["app"], "Adobe Photoshop 2025")

    def test_title_match(self) -> None:
        self.assertEqual(pick_window([CHESS, FINDER], "downloads")["app"], "Finder")

    def test_exact_app_beats_title_substring(self) -> None:
        notes = {"app": "Notes", "title": "Chess openings", "width": 900, "height": 900}
        self.assertEqual(pick_window([notes, CHESS], "chess")["app"], "Chess")

    def test_no_match_raises(self) -> None:
        with self.assertRaises(WindowNotFound) as ctx:
            pick_window([CHESS, FINDER], "Photoshop")
        self.assertIn("Chess", str(ctx.exception))

    def test_frontmost_wins_without_target(self) -> None:
        self.assertEqual(pick_window([CHESS, FINDER], None)["app"], "Finder")

    def test_largest_without_target_or_frontmost(self) -> None:
        windows = [
            {"app": "A", "title": "", "width": 10, "height": 10},
            {"app": "B", "title": "", "width": 40, "height": 40},
        ]
        self.assertEqual(pick_window(windows, None)["app"], "B")

    def test_find_window_by_app_and_title(self) -> None:
        other = {**CHESS, "title": "Game 2", "x": 999}
        self.assertEqual(find_window([other, CHESS], "Chess", "Game 1")["x"], 100)
        self.assertIsNone(find_window([other, {**CHESS, "title": "Game 3"}], "Chess", "Game 1"))


if __name__ == "__main__":
    unittest.main()
