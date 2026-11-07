---
name: hud-teach
description: Teach the user step by step on any live Mac window with numbered click-through marks and an on-screen step card.
version: 0.2.0
author: Luke The Dev (@iamlukethedev)
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [desktop, hud, teach, tutorial]
    category: desktop
---

# HUD Teach Skill

Paint numbered, click-through marks and a short step card on the real Mac window
the user is looking at (chess, a browser game, Photoshop, a DAW, System Settings)
instead of narrating menu paths. The user keeps the mouse. Do not click for them
unless they asked Hermes to do the work.

## When to Use

- "Teach me how to…", "show me where…", "how do I…", "walk me through…".
- Chess or game coaching: arrows and circles on the live board while they play.
- Any visible desktop app where pointing beats describing.

## Prerequisites

- macOS with Screen Recording granted to Hermes Desktop (or the terminal running
  Hermes). Accessibility as well, to find windows by name.
- If capture or draw fails, call `teach_screen action=check` and relay the
  `next_steps` to the user. The user can also run `/teach check`.

## The lesson loop

1. **Capture.** `teach_screen action=capture target=<app or window title>`.
   Without `target` you get the frontmost app's largest window. If the target is
   not found, the error lists the visible apps: pick one or ask.
2. **Plan.** Look at the screenshot. Break the task into at most 12 short
   steps. Only the steps for *this* screen get marks; later screens come later.
3. **Draw the current step.** `teach_screen action=draw` with:
   - `shapes`: marks in pixels of the screenshot, (0, 0) top-left. Put
     `step: N` on the mark for step N, and a 1–4 word `label` if it helps
     ("File menu", "Knight").
   - `title`: the lesson in a few words ("Export as PNG").
   - `steps`: every step as `{text}`, in order, `done: true` on finished ones.
   - `current_step`: the step to do now. Its badge pulses and the card
     highlights it.
   Frame size and window position come from the last capture; do not pass
   `frame_width`, `frame_height` or `bounds` unless overriding.
4. **Say it once.** One line per step in chat, numbers matching the badges.
5. **Advance.** When the user says done, or the UI changed, capture again and
   draw the next step with earlier steps `done: true`. A new draw replaces the
   old marks. Skip the recapture only if nothing on screen moved.
6. **Finish.** On the last step, mark everything done, congratulate briefly,
   then `action=clear` (or let the TTL expire).

## Example draw

```json
{
  "action": "draw",
  "title": "Export as PNG",
  "steps": [
    {"text": "Open the File menu", "done": true},
    {"text": "Choose Export → Export As…"},
    {"text": "Pick PNG, then Export"}
  ],
  "current_step": 2,
  "shapes": [
    {"kind": "rect", "x": 412, "y": 188, "width": 210, "height": 26, "step": 2, "color": "yellow", "label": "Export As…"},
    {"kind": "arrow", "fromX": 300, "fromY": 260, "toX": 405, "toY": 201, "color": "yellow"}
  ]
}
```

## Quick Reference

| Action | What it does |
|---|---|
| `capture` | Screenshot + geometry remembered for the next draw |
| `draw` | Marks + optional step card (`title`, `steps`, `current_step`) |
| `clear` | Remove the marks |
| `list` | Visible windows (app, title, position) |
| `status` | What is on screen and the last capture |
| `check` | Permissions, Tk and overlay health, with fixes |

Shape kinds: `circle` (x, y, radius), `rect` (x, y, width, height), `arrow` /
`line` (fromX, fromY, toX, toY; arrows point at `to`), `polyline` (points),
`label` (x, y, text). Options: `step` 1–12, `color` (`red`, `orange`, `yellow`,
`green`, `blue`, `purple`, `white`, `black`), `label`, `dashed`, `fill` (rect).
`legend_position` places the card (`auto` avoids your marks). `ttl_seconds`
defaults to 180, max 900.

## Pitfalls

- Coordinates are screenshot pixels, not screen points. The tool rejects marks
  far outside the image; re-read the screenshot instead of guessing.
- A window resized since the capture is refused: capture again. A moved window
  is followed automatically.
- Missing Screen Recording looks like a failed capture or a wallpaper-only
  image, not a missing tool. Run `check`.
- Keep `steps` text short (under ~60 characters reads best on the card).
- Marks are click-through. If clicks land on the marks, `clear` and draw again.

## Verification

Marks land on the named controls, the current step's badge pulses, the card
shows the right step, clicks pass through to the app, and the marks disappear
after the TTL, on `action=clear`, or when the conversation ends.
