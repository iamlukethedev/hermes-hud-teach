# Changelog

## 0.2.0

Lessons, reliability, and a first-run path that tells you what is wrong.

### New

- **Step card lessons.** `draw` takes `title`, `steps` (each `{text, done}`) and
  `current_step`. The overlay shows a card with the lesson, ticks finished steps,
  highlights the current one, and pulses the current step's badge on screen. The
  card picks the corner with the fewest marks (or `legend_position`).
- **Labels on marks.** A shape's `label` now renders beside its badge. It was
  accepted before but never drawn.
- **`check` action, `/teach` and `hermes hud-teach`.** `check`, `demo [app]`,
  `status`, `clear` and `stop`. `check` reports macOS, Tk, Accessibility,
  Screen Recording and overlay health with the fix for each failure. `demo` draws
  a 30-second sample lesson on the frontmost window, so you can confirm the
  setup without an agent turn.
- **Bundled skill is registered.** `skills/hud-teach/SKILL.md` was shipped but
  never registered, so the agent never saw it. It is now `hud-teach:hud-teach`
  and describes the capture → step → recapture lesson loop.
- **Live Desktop chip.** The status bar shows `teach · step 2/5` or the mark
  count while marks are up, and a click clears them. New palette command:
  **Check HUD Teach setup**.

### Fixed

- **Marks no longer vanish when Hermes finishes its reply.** Cleanup ran on
  `on_session_end`, which fires after every turn, so marks were cleared right
  after they were explained. Cleanup now runs on `on_session_finalize` (`/new`,
  exit, gateway reset).
- **`draw` remembers the last capture.** `frame_width`, `frame_height` and
  `bounds` default to it, so a mis-copied number can no longer misplace every
  mark. Optional `capture_id` refuses to draw on a superseded capture.
- **Moved windows are followed; resized windows are refused** with a request to
  capture again, instead of drawing in the wrong place.
- **A `target` that matches nothing is an error listing the visible apps**,
  instead of silently capturing the largest window.
- **Full-display fallback lines up.** Without a window list, the overlay used
  the shrunken JPEG size as the screen size; it now covers the real display.
- **Out-of-frame coordinates are rejected** with the offending shape and the
  frame size.
- **Tool schema is provider-safe.** `shapes` and `steps` declare `items`.
  Some providers reject arrays without them.
- Runtime state moved to `<HERMES_HOME>/plugin-data/hud-teach/`. The daemon
  socket is user-only (`0600`), and the daemon is pinned to the plugin's state
  directory. An idle overlay process exits after 30 minutes with nothing on
  screen.

### Tests and CI

- Tests run on Linux and macOS. The Tk overlay daemon is exercised end to end
  under Xvfb: draw a lesson, read the state back, TTL expiry, and clear.
- CI runs `hermes plugins validate --install-deps`, the catalog admission
  check, on every push.

## 0.1.3

- Numbered click-through marks on any live Mac window (`list`, `capture`,
  `draw`, `clear`, `status`).
