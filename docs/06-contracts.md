# 06 · Contracts

**Status: DRAFT.** Agree these at the Sat 12:00 checkpoint, then change them only with both owners present. Record every change at the bottom of this file.

## Robot interface (ARM → BRAIN)

Defined in [`contracts/robot.py`](../contracts/robot.py). Both `robot/` (real arm) and the fake robot implement it.

| Call | Returns | Notes |
|---|---|---|
| `home()`, `park()` | `None` | `park` keeps the arm over the tray, clear of the iron |
| `go_pose(name)` | `None` | Any taught pose by name |
| `gripper(norm)` | `None` | `j8` in `position_norm`; open about 0.78 |
| `fetch_cup(slot)` | `FetchResult` | Whole motion: tray → handover → home. `gripped=False` when no load was sensed |
| `go_inspect(area)` | `None` | Wrist camera over the board area |
| `camera_jpeg(cam, max_px=640)` | `bytes` | `cam` is `"side"` or `"wrist"` |
| `joints()` | `dict[str, float]` | `j1`..`j8` from the motor bus |
| `stop()` | `None` | Abort the current motion and hold |

## MCP tools (BRAIN, called by Claude)

| Tool | Arguments | What it does |
|---|---|---|
| `fetch_part` | `ref` or `slot`, `speed="normal"` | Looks up the cup for the part and runs `fetch_cup` |
| `look` | `camera="side"` | Returns a frame plus a check: is the cup in the handover zone |
| `show_footprint` | `ref` | Lights up the footprint on the bench screen |
| `inspect` | `area` or `ref` | Moves the wrist camera and classifies each joint |
| `mark_joint` | `ref`, `pad`, `kind`, `text` | Circles a pad on the bench screen (`cold`, `bad`, `ok`) |
| `speak` | `text` | Says a sentence out loud |
| `status` | | Build progress, last errors, joint temperatures |

## Bench screen API (BRAIN → SCREEN)

`screen/bench-screen/guide_control.py`, already working. It writes `guide_state.json`; the page polls it every 250 ms.

```python
from guide_control import show, placed, inspect, flag, clear, done
show("D2", "Band goes to the lower pad.")   # light up a footprint
placed("D2")                                 # mark it soldered
flag("C4", 2, "cold", "reheat 3 s")          # circle pad 2 of C4
done(led=True)                               # power stage finished, D1 on
```

## Build plan (BRAIN's planner → screen and agent)

One JSON file, [`contracts/build_plan.example.json`](../contracts/build_plan.example.json), is the single source for part order, cups, footprints, pads and polarity notes. The bench screen's `TARGETS` and Claude's instructions are generated from it once the planner (B3) exists; until then `TARGETS` in `screen/bench-screen/bench-screen.js` is the source.

## Change log

| When | Change | Agreed by |
|---|---|---|
| | | |
