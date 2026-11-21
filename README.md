# Third Hand

A voice-driven electronics build assistant on NormaCore's ElRobot arm, built for the **NormaCore "AI-Powered Robot Control"** track at the AI × Robotics Hackathon II (CIC Berlin, 21–22 November 2026).

**Current plan: the resistor picker ([docs/10](docs/10-plan-resistor-picker.md)).** You build an LED circuit on a breadboard and say which LED comes next. Claude works out the resistor, reads the colour bands of every resistor on a rack through the wrist camera, and the arm picks the right one. A SmolVLA policy that we fine-tune on NormaCore's stack does the grasp. Claude then shows on the bench screen where the resistor goes.

## The loop for one resistor

1. You say "blue LED on pin 10". The circuit is an Arduino Uno and a breadboard: two LEDs and a button, powered over USB ([`board/led-circuit.json`](board/led-circuit.json)).
2. Claude works out 150 Ω (brown, green, brown) and says it; `show_step` puts the calculation on the screen.
3. `scan_rack`: the wrist camera passes over the six slots, and Claude reads each resistor.
4. `pick(slot)`: the arm hovers over the slot, the fine-tuned policy grasps the resistor (a scripted grasp is the fallback), and the arm drops it in the dish by your hand.
5. You plug it into the breadboard while the screen shows the holes. If someone swaps resistors, Claude scans again.

The first plan, the SOL-MIO cup demo, is in docs 04, 05 and 08, marked as superseded.

## Repository map

| Path | What lives there | Owner |
|---|---|---|
| [`docs/`](docs) | Research findings and plans. Start with 04 (demo) and 05 (team plan). | everyone |
| [`contracts/`](contracts) | Interfaces between workstreams. **Draft until the Sat 12:00 checkpoint.** | BRAIN |
| [`robot/`](robot) | Station setup, robot library, taught poses, motions, fake robot | ARM |
| [`agent/`](agent) | MCP server, Claude instructions, vision checks, board planner | BRAIN |
| [`screen/`](screen) | Bench screen, voice, AR overlay, stage dashboard | SCREEN |
| [`board/`](board) | SOL-MIO data, parts and cup map, reference joint photos | BENCH |
| [`sim/`](sim) | 3D simulation of the whole demo with the real ElRobot model | reference |

## Quick start

Robot (full steps in [robot/normacore/README.md](robot/normacore/README.md)):

```bash
bash robot/normacore/install_station.sh
```

```bash
bash robot/normacore/run_station.sh
```

```bash
python3 robot/normacore/examples/01_list_buses.py
```

Bench screen (the monitor next to the bench):

```bash
cd screen/bench-screen && python3 -m http.server 8077
```

Open http://localhost:8077 and press F for fullscreen. Drive it from a second terminal:

```bash
python3 screen/bench-screen/guide_control.py show D2
```

3D simulation of the demo:

```bash
cd sim && python3 -m http.server 8000
```

Open http://localhost:8000.

## Team and working rules

Four roles, one owner each: **ROBOT** (robot and data), **VLA** (fine-tuning), **AGENT** (Claude and vision), **BENCH** (circuit, screen and story). Tasks, checkpoints and sleep shifts are in [docs/10-plan-resistor-picker.md](docs/10-plan-resistor-picker.md), with live status at https://claude.ai/artifact/DuCRQLU5JGacwz4uvjZpJj.

- Everyone runs Claude Code from the repo root. [`CLAUDE.md`](CLAUDE.md) holds the rules it follows.
- Contracts first: nobody changes `contracts/` without the other side agreeing.
- Branch per workstream (`arm/...`, `brain/...`, `screen/...`, `bench/...`). Merge to `main` at checkpoints. `main` must always run the demo.
- Feature freeze **Sunday 12:00**. Submission **Sunday 17:45**. Pitch **Sunday 19:00**. All times Berlin.

## Documents

1. [Hackathon facts](docs/01-hackathon.md): tracks, schedule, what we know about judging
2. [NormaCore Station and ElRobot](docs/02-normacore-station.md): API, queues, registers, cameras, gotchas
3. [Lessons from the June winner](docs/03-june-winner-lessons.md): what won this track last time and what to reuse
4. [Demo design](docs/04-demo-design.md): concept, bench layout, parts, stage script
5. [Team plan](docs/05-team-plan.md): workstreams, deliverables, timeline
6. [Contracts](docs/06-contracts.md): robot interface, MCP tools, screen API, build plan format
7. [Risks](docs/07-risks.md): what can break on stage and the fallback for each
8. [Bench and parts](docs/08-bench-and-parts.md): parts, cups, bench kit, pre-event checklist
9. [Architecture](docs/09-architecture.md): processes, Hub API, MCP tools, build state, safety layers (proposal)
10. **[Plan v2: the resistor picker](docs/10-plan-resistor-picker.md): current demo, system, tasks per person, checkpoints, fallbacks**

## Prior work and credits

Prepared before the event: the research notes in `docs/`, the 3D simulation in `sim/` and the bench screen prototype in `screen/bench-screen/`. Check the hackathon's rules on pre-existing code and say this in the submission. Details and third-party credits are in [NOTICE.md](NOTICE.md).
