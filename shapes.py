"""Validate and normalize teach_screen draw payloads."""

from __future__ import annotations

from typing import Any, Optional

COLORS = ("black", "blue", "green", "orange", "purple", "red", "white", "yellow")
KINDS = ("circle", "rect", "arrow", "line", "polyline", "label")
MAX_STEP = 12
MAX_SHAPES = 24
MAX_POLYLINE_POINTS = 64
MAX_LABEL = 80


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
    return None


def scale_xy(x: float, y: float, frame_width: float, frame_height: float, overlay_w: float, overlay_h: float) -> tuple[float, float]:
    """Map screenshot pixels into overlay-local points."""
    sx = overlay_w / frame_width if frame_width else 1.0
    sy = overlay_h / frame_height if frame_height else 1.0
    return x * sx, y * sy
