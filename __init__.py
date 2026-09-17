"""hud-teach — numbered how-to marks on the live Mac app under Hermes."""

from __future__ import annotations

import logging
import platform

from .teach import SCHEMA, handle_teach_screen, macos_only

logger = logging.getLogger(__name__)


def _on_session_end(**_kwargs) -> None:
    """Drop leftover marks when the conversation ends."""
    try:
        from .overlay import clear

        clear()
    except Exception as exc:
        logger.debug("hud-teach session-end clear skipped: %s", exc)


def register(ctx) -> None:
    """Register the teach_screen tool and a session-end cleanup hook."""
    if platform.system() != "Darwin":
        logger.info("hud-teach: skipping registration on %s (macOS only)", platform.system())
        return

    ctx.register_tool(
        name="teach_screen",
        toolset="hud_teach",
        schema=SCHEMA,
        handler=lambda args, **kw: handle_teach_screen(
            action=args.get("action", "status"),
            target=args.get("target"),
            shapes=args.get("shapes"),
            frame_width=args.get("frame_width"),
            frame_height=args.get("frame_height"),
            bounds=args.get("bounds"),
            ttl_seconds=args.get("ttl_seconds"),
        ),
        check_fn=macos_only,
        description=SCHEMA["description"],
        emoji="📌",
    )
    ctx.register_hook("on_session_end", _on_session_end)
