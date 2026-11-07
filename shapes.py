"""Validate and normalize teach_screen draw payloads."""

from __future__ import annotations

from typing import Any, Iterable, Optional

COLORS = ("black", "blue", "green", "orange", "purple", "red", "white", "yellow")
KINDS = ("circle", "rect", "arrow", "line", "polyline", "label")
MAX_STEP = 12
MAX_SHAPES = 24
MAX_POLYLINE_POINTS = 64
MAX_LABEL = 80
MAX_TITLE = 80
MAX_STEP_TEXT = 120
# Marks may sit slightly outside the capture (a badge on a window edge), not far off it.
FRAME_SLACK = 0.05
LEGEND_POSITIONS = ("auto", "top-left", "top-right", "bottom-left", "bottom-right")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _validate_step(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1 or raw > MAX_STEP:
        return f"step must be an integer from 1 to {MAX_STEP}."
    return None


def _point(value: Any, label: str) -> Optional[str]:
    if not isinstance(value, dict):
        return f"{label} must be an object with x and y."
    if not _is_number(value.get("x")) or not _is_number(value.get("y")):
        return f"{label} needs numeric x and y."
    return None


def validate_shape(index: int, shape: Any) -> Optional[str]:
    """Return an error string for one shape, or None if it is usable."""
    prefix = f"shapes[{index}]"
    if not isinstance(shape, dict):
        return f"{prefix} must be an object."
    kind = shape.get("kind")
    if kind not in KINDS:
        return f"{prefix}.kind must be one of: {', '.join(KINDS)}."
    color = shape.get("color", "red")
    if color not in COLORS:
        return f"{prefix}.color must be one of: {', '.join(COLORS)}."
    step_err = _validate_step(shape.get("step"))
    if step_err:
        return f"{prefix}.{step_err}"
    label = shape.get("label")
    if label is not None and (not isinstance(label, str) or len(label) > MAX_LABEL):
        return f"{prefix}.label must be a string of at most {MAX_LABEL} characters."

    if kind == "circle":
        if not _is_number(shape.get("x")) or not _is_number(shape.get("y")):
            return f"{prefix} circle needs numeric x and y."
        radius = shape.get("radius")
        if not _is_number(radius) or radius <= 0:
            return f"{prefix} circle needs a positive radius."
        return None

    if kind == "rect":
        for key in ("x", "y", "width", "height"):
            if not _is_number(shape.get(key)):
                return f"{prefix} rect needs numeric {key}."
        if shape["width"] <= 0 or shape["height"] <= 0:
            return f"{prefix} rect width and height must be positive."
        return None

    if kind in ("arrow", "line"):
        for key in ("fromX", "fromY", "toX", "toY"):
            if not _is_number(shape.get(key)):
                return f"{prefix} {kind} needs numeric {key}."
        return None

    if kind == "polyline":
        points = shape.get("points")
        if not isinstance(points, list) or len(points) < 2:
            return f"{prefix} polyline needs at least two points."
        if len(points) > MAX_POLYLINE_POINTS:
            return f"{prefix} polyline is capped at {MAX_POLYLINE_POINTS} points."
        for i, point in enumerate(points):
            err = _point(point, f"{prefix}.points[{i}]")
            if err:
                return err
        return None

    text = shape.get("text")
    if not isinstance(text, str) or not text.strip():
        return f"{prefix} label needs non-empty text."
    if len(text) > MAX_LABEL:
        return f"{prefix} label text is capped at {MAX_LABEL} characters."
    if not _is_number(shape.get("x")) or not _is_number(shape.get("y")):
        return f"{prefix} label needs numeric x and y."
    return None


def shape_points(shape: dict[str, Any]) -> Iterable[tuple[float, float]]:
    """Every screenshot-pixel point a validated shape touches."""
    kind = shape.get("kind")
    if kind == "circle":
        x, y, r = float(shape["x"]), float(shape["y"]), float(shape["radius"])
        yield from ((x - r, y), (x + r, y), (x, y - r), (x, y + r))
    elif kind == "rect":
        x, y = float(shape["x"]), float(shape["y"])
        w, h = float(shape["width"]), float(shape["height"])
        yield from ((x, y), (x + w, y + h))
    elif kind in ("arrow", "line"):
        yield (float(shape["fromX"]), float(shape["fromY"]))
        yield (float(shape["toX"]), float(shape["toY"]))
    elif kind == "polyline":
        for p in shape["points"]:
            yield (float(p["x"]), float(p["y"]))
    elif kind == "label":
        yield (float(shape["x"]), float(shape["y"]))


def check_in_frame(shapes: list[dict[str, Any]], frame_width: float, frame_height: float) -> Optional[str]:
    """Reject marks that land well outside the screenshot they claim to come from."""
    lo_x, hi_x = -frame_width * FRAME_SLACK, frame_width * (1 + FRAME_SLACK)
    lo_y, hi_y = -frame_height * FRAME_SLACK, frame_height * (1 + FRAME_SLACK)
    for i, shape in enumerate(shapes):
        for x, y in shape_points(shape):
            if not (lo_x <= x <= hi_x and lo_y <= y <= hi_y):
                return (
                    f"shapes[{i}] reaches ({x:g}, {y:g}), outside the {frame_width:g}x{frame_height:g} "
                    "capture. Coordinates are screenshot pixels with (0, 0) at the top-left of the "
                    "captured image."
                )
    return None


def validate_lesson(title: Any, steps: Any, current_step: Any, legend_position: Any) -> Optional[str]:
    """Validate the optional on-screen step card."""
    if title is not None and (not isinstance(title, str) or len(title) > MAX_TITLE):
        return f"title must be a string of at most {MAX_TITLE} characters."
    if steps is not None:
        if not isinstance(steps, list):
            return "steps must be an array of strings or {text, done} objects."
        if len(steps) > MAX_STEP:
            return f"steps is capped at {MAX_STEP} entries."
        for i, step in enumerate(steps):
            text = step.get("text") if isinstance(step, dict) else step
            if not isinstance(text, str) or not text.strip():
                return f"steps[{i}] needs non-empty text."
            if len(text) > MAX_STEP_TEXT:
                return f"steps[{i}] text is capped at {MAX_STEP_TEXT} characters."
            if isinstance(step, dict) and "done" in step and not isinstance(step["done"], bool):
                return f"steps[{i}].done must be true or false."
    if current_step is not None:
        err = _validate_step(current_step)
        if err:
            return f"current_{err}"
        if isinstance(steps, list) and steps and current_step > len(steps):
            return f"current_step {current_step} is past the {len(steps)} listed steps."
    if legend_position is not None and legend_position not in LEGEND_POSITIONS:
        return f"legend_position must be one of: {', '.join(LEGEND_POSITIONS)}."
    return None


def normalize_steps(steps: Any) -> list[dict[str, Any]]:
    """Turn validated steps into [{n, text, done}] for the overlay."""
    out = []
    for i, step in enumerate(steps or []):
        if isinstance(step, dict):
            out.append({"n": i + 1, "text": step["text"].strip(), "done": bool(step.get("done"))})
        else:
            out.append({"n": i + 1, "text": str(step).strip(), "done": False})
    return out


def validate_draw_payload(shapes: Any, frame_width: Any, frame_height: Any) -> Optional[str]:
    """Return an error string for a draw call, or None if it can be painted."""
    if not _is_number(frame_width) or frame_width <= 0 or not _is_number(frame_height) or frame_height <= 0:
        return "draw needs frame_width and frame_height from the screenshot you just captured."
    if not isinstance(shapes, list) or not shapes:
        return "draw needs a non-empty shapes array."
    if len(shapes) > MAX_SHAPES:
        return f"draw is capped at {MAX_SHAPES} shapes."
    for i, shape in enumerate(shapes):
        err = validate_shape(i, shape)
        if err:
            return err
    return check_in_frame(shapes, float(frame_width), float(frame_height))


def scale_xy(x: float, y: float, frame_width: float, frame_height: float, overlay_w: float, overlay_h: float) -> tuple[float, float]:
    """Map screenshot pixels into overlay-local points."""
    sx = overlay_w / frame_width if frame_width else 1.0
    sy = overlay_h / frame_height if frame_height else 1.0
    return x * sx, y * sy


def pick_legend_corner(
    shapes: list[dict[str, Any]], frame_width: float, frame_height: float, preferred: str = "auto"
) -> str:
    """Pick the corner the step card covers least of the marks (ties go top-right)."""
    if preferred in LEGEND_POSITIONS and preferred != "auto":
        return preferred
    corners = {"top-right": 0, "top-left": 0, "bottom-right": 0, "bottom-left": 0}
    qw, qh = frame_width * 0.45, frame_height * 0.45
    for shape in shapes:
        for x, y in shape_points(shape):
            if y <= qh and x >= frame_width - qw:
                corners["top-right"] += 1
            if y <= qh and x <= qw:
                corners["top-left"] += 1
            if y >= frame_height - qh and x >= frame_width - qw:
                corners["bottom-right"] += 1
            if y >= frame_height - qh and x <= qw:
                corners["bottom-left"] += 1
    return min(corners, key=lambda name: corners[name])
