---
name: hud-teach
description: Draw numbered how-to marks on the live Mac app.
version: 0.1.0
author: Luke The Dev (@iamlukethedev)
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [desktop, hud, teach]
    category: desktop
---

# HUD Teach Skill

Puts numbered, click-through marks on the real Mac app the user is looking at
(Photoshop, a DAW, Settings) instead of narrating menu paths. It does not click
for the user unless they asked Hermes to do the work.

## When to Use

- "Teach me how to…", "how do I…", "highlight the steps on screen."
- The user has a desktop app visible and wants marks on the live UI.

## Prerequisites

- macOS. Screen Recording for Hermes Desktop (or the terminal running Hermes).
- Accessibility if the user wants a specific window listed by name.

## How to Run

1. `teach_screen` with `action=capture` and optional `target` (e.g. `Photoshop`).
2. Read the screenshot. Plan at most 12 steps for the *current* screen.
3. `teach_screen` with `action=draw`, the capture's `frame_width`, `frame_height`,
   and `bounds`, plus `shapes` that include `step` 1–12. `ttl_seconds` ~180.
4. After the UI changes, capture again and draw the next screen. Do not stack
   two walkthroughs; a new draw replaces the previous marks.

## Quick Reference

| Action | What it does |
|---|---|
| `list` | Visible windows (app, title, DIP bounds) |
| `capture` | Screenshot + `frame_width` / `frame_height` / `bounds` |
| `draw` | Paint numbered marks (screenshot-pixel coordinates) |
| `clear` | Remove marks |
| `status` | Whether the overlay process is running |

Shape kinds: `circle`, `rect`, `arrow`, `line`, `polyline`, `label`. Colors:
`red`, `orange`, `yellow`, `green`, `blue`, `purple`, `white`, `black`.

## Procedure

1. Capture the target app, not Hermes itself.
2. Point marks at the real control (button, menu, panel). Keep labels short.
3. Leave the mouse to the user. Do not click the target app unless they asked
   you to perform the steps.
4. Say what to click in one line each, matching the badge numbers on screen.

## Pitfalls

- Coordinates are **screenshot pixels**, not DIP. Always reuse the capture's
  `frame_width` / `frame_height` / `bounds`.
- Missing Screen Recording looks like a failed capture, not a missing tool.
- The overlay is click-through. If clicks hit the marks instead of Photoshop,
  the window did not ignore mouse events — `clear` and draw again.

## Verification

Marks land on the named controls, stay click-through, and disappear after TTL
or `action=clear`.
