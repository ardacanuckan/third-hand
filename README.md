# Third Hand

A voice-driven soldering assistant on NormaCore's ElRobot arm, built for the **NormaCore "AI-Powered Robot Control"** track at the AI × Robotics Hackathon II (CIC Berlin, 21–22 November 2026).

You hold the iron and talk. Claude has the arm fetch each part, lights up where it goes on a bench screen, and checks every solder joint with the wrist camera. The demo board is a fresh **SOL-MIO v1.3**, the controller of our soft rehabilitation glove. In the finale, a finished SOL-MIO drives the glove.

## The loop for one part

1. You say "next part".
2. Claude picks the part from the build plan and calls `show_footprint`. The bench screen lights up its footprint.
3. The arm brings the cup holding that part to the handover zone (`fetch_part`).
4. The side camera confirms the cup arrived (`look`). If it did not, Claude says so and retries.
5. You place and solder the part.
6. After the last part, the wrist camera inspects every joint (`inspect`). A cold joint gets circled on the screen (`mark_joint`) and Claude tells you how to fix it.

Why a screen instead of the gripper pointing: the ElRobot's jaws are far wider than a 0603 resistor or a 1206 LED, so pointing with them is imprecise and covers the part. See [docs/04-demo-design.md](docs/04-demo-design.md).

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

Four workstreams, one owner each: **ARM** (robot runtime), **BRAIN** (agent), **SCREEN** (experience), **BENCH** (product, hardware and story). Deliverables, checkpoints and sleep shifts are in [docs/05-team-plan.md](docs/05-team-plan.md).

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

## Prior work and credits

Prepared before the event: the research notes in `docs/`, the 3D simulation in `sim/` and the bench screen prototype in `screen/bench-screen/`. Check the hackathon's rules on pre-existing code and say this in the submission. Details and third-party credits are in [NOTICE.md](NOTICE.md).
