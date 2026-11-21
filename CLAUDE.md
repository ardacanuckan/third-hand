# CLAUDE.md

Guidance for Claude Code in this repository. Every teammate runs Claude Code from the repo root, so these rules apply to all four workstreams.

## What we are building

Third Hand: a voice-driven electronics build assistant on NormaCore's ElRobot (8 ST3215 servos, 7 joints plus jaws) and NormaCore Station.

**Current plan (since Sat 15:30): the resistor picker.**
- The person builds an Arduino Uno LED circuit on a breadboard, with no soldering.
- Claude works out each resistor and reads the colour bands of the resistors on a rack through the wrist camera.
- The arm picks the right one: a SmolVLA policy fine-tuned with NormaCore's `smolvla_py` does the grasp, with a scripted grasp as the fallback.

Read `docs/10-plan-resistor-picker.md` before making product decisions. Docs 04, 05 and 08 (the SOL-MIO cup demo) are superseded.

## Repo map

- `contracts/` interfaces between workstreams. Do not change a contract without the owners on both sides agreeing; note the change in `docs/06-contracts.md`.
- `robot/` (ARM) Station integration, `robot_lib`, poses, motions, `FakeRobot`.
- `agent/` (BRAIN) MCP server, prompts, vision checks, board planner.
- `screen/` (SCREEN) bench screen, voice, AR overlay, stage dashboard. `screen/bench-screen/` already works.
- `board/` (BENCH) board data, parts and cups, reference photos.
- `sim/` reference 3D simulation. Do not build features on it during the event.

## Hardware safety (non-negotiable)

- Start Station with `-t`; the API on port 8888 does not exist otherwise.
- Pin the follower bus serial in `station.yaml`. **Never send commands to the leader bus.**
- All motion goes through `robot_lib` functions that clamp targets to calibrated ranges and limit the step per call. The model never sends raw register writes.
- The shoulder (`j2`) faults under load when commanded straight to a reach pose: move in small steps and tuck the elbow (`j3`) before lifting the shoulder.
- Read joint state from the motor bus (`st3215/inference`), not from camera frames; the camera bridge can freeze.
- Someone stays at the power switch whenever the arm moves. Keep speed low near hands.

## Conventions

- Python 3.11+, type hints, `uv` for environments. Small modules; no global state shared between workstreams.
- Joint values are Station's normalized `position_norm` (0..1) unless a name says `_rad` or `_raw`.
- Board coordinates are millimetres in the SOL-MIO Altium frame (origin bottom left, y up). Part refs are the board's refdes (`D2`, `R1`, ...).
- Cup slots are `A1`..`B3` (see `docs/08-bench-and-parts.md`).
- Camera images sent to Claude: JPEG, longest side about 640 px.
- One tool call should run one whole motion. Do not make Claude micro-manage joints.

## Workflow

- Branch per workstream: `arm/<topic>`, `brain/<topic>`, `screen/<topic>`, `bench/<topic>`.
- Merge to `main` at checkpoints (see `docs/05-team-plan.md`). Never merge in the last hour before a checkpoint. `main` always runs the demo.
- Feature freeze Sunday 12:00 Berlin. After that, only fixes for what breaks in rehearsal.
- When you finish a deliverable, update its status in the team tracker and mention it in your PR.

## Useful commands

```bash
cd screen/bench-screen && python3 -m http.server 8077        # bench screen
python3 screen/bench-screen/guide_control.py show D2          # light up D2
cd sim && python3 -m http.server 8000                        # 3D simulation
```
