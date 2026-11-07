"""hud-teach — numbered how-to marks and step-by-step lessons on the live Mac app under Hermes."""

from __future__ import annotations

import logging
import platform
from pathlib import Path

from .teach_commands import run_cli, setup_cli, slash_command
from .teach import SCHEMA, handle_teach_screen, macos_only

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).resolve().parent / "skills"
TOOL_ARGS = (
    "target", "shapes", "frame_width", "frame_height", "bounds", "ttl_seconds",
    "title", "steps", "current_step", "legend_position", "capture_id",
)


def _on_session_finalize(**_kwargs) -> None:
    """Drop leftover marks when the conversation is torn down (/new, exit, gateway reset).

    Not on_session_end: that fires after every turn, which would wipe the marks the
    moment Hermes finishes explaining them.
    """
    try:
        from .overlay import clear

        clear()
    except Exception as exc:
        logger.debug("hud-teach session-finalize clear skipped: %s", exc)


def _tool_handler(args, **_kw):
    return handle_teach_screen(action=args.get("action", "status"), **{k: args.get(k) for k in TOOL_ARGS})


def _register_skills(ctx) -> None:
    if not SKILLS_DIR.is_dir():
        return
    for child in sorted(SKILLS_DIR.iterdir()):
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.exists():
            try:
                ctx.register_skill(child.name, skill_md)
            except Exception as exc:
                logger.warning("hud-teach: could not register skill %s: %s", child.name, exc)


def register(ctx) -> None:
    """Register teach_screen, its skill, /teach, `hermes hud-teach`, and session cleanup.

    Availability is gated by check_fn=macos_only so catalog validation still
    sees the declared tool on Linux CI. The handler refuses non-macOS drawing.
    """
    if platform.system() != "Darwin":
        logger.info("hud-teach: registering on %s; teach_screen is unavailable until macOS", platform.system())

    ctx.register_tool(
        name="teach_screen",
        toolset="hud_teach",
        schema=SCHEMA,
        handler=_tool_handler,
        check_fn=macos_only,
        description=SCHEMA["description"],
        emoji="📌",
    )
    ctx.register_hook("on_session_finalize", _on_session_finalize)
    _register_skills(ctx)
    try:
        ctx.register_command(
            "teach",
            handler=slash_command,
            description="HUD Teach: check setup, run a demo lesson, show status, or clear marks",
            args_hint="<check|demo|status|clear|stop>",
        )
        ctx.register_cli_command(
            name="hud-teach",
            help="HUD Teach: check setup, demo, status, clear",
            setup_fn=setup_cli,
            handler_fn=run_cli,
        )
    except Exception as exc:
        logger.warning("hud-teach: /teach and `hermes hud-teach` unavailable: %s", exc)
