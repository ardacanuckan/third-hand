# 05 · Team plan

Four people, four workstreams. Each person owns a whole system and one moment on stage. Claude Code makes each of us several times faster, so the plan is bigger than a normal hackathon plan. All times Berlin.

Live tracker with shared status and owner names: https://claude.ai/artifact/DuCRQLU5JGacwz4uvjZpJj (private; ask the BENCH owner for Contributor access).

## How we work with AI

1. **Contracts first.** The robot interface and screen API freeze at Sat 12:00; after that everyone builds in parallel.
2. **Nobody waits for hardware.** A `FakeRobot` with the real interface lets BRAIN and SCREEN test the full loop from hour one.
3. **One repo, one CLAUDE.md.** Each person runs Claude Code in their own folder; the root file holds the rules.
4. **AI writes code, people do the physical work.** Wrappers, UIs, tests, calibration tools and prompts go to Claude. Teaching poses, soldering, tuning and decisions stay with people.
5. **Main always runs the demo.** Merge at every checkpoint, never in the last hour before one.

## ARM · Robot runtime

*Mission:* the ElRobot as a dependable library; every motion is one call that works 10 out of 10. *On stage:* the fetch and the missed grip that fixes itself. *Best fit:* has used servos, ROS or LeRobot.

| ID | Deliverable | Window | Done when |
|---|---|---|---|
| A1 | Fake robot with the real interface (logs moves, canned frames, can miss a grip) | Sat 11:00–12:30 | BRAIN runs a full loop on it |
| A2 | Station bring-up, `robot_lib` ported from the June winner (credit) | Sat 11:00–13:30 | Joints live and a frame from each camera |
| A3 | Pose teaching tool (torque off, move, name, save, replay) | Sat 12:30–15:00 | All poses saved and replayable |
| A4 | Motion skills: `fetch_cup`, `place_handover`, `go_inspect`, `park`, `home`; overload-safe, stall stop, e-stop key | Sat 14:00–18:00 | `fetch_cup` 10/10 for every cup |
| A5 | Reliability harness: 50 unattended cycles with temperatures and currents | Sat 18:00–22:00 | 48 or more of 50 succeed |
| A6 | *Stretch:* every build tagged in Station and exported as a LeRobot dataset | Sat 22:00–Sun 02:00 | One build opens in the dataset viewer |

## BRAIN · Agent

*Mission:* one spoken sentence becomes the right tools in the right order, with eyes on the result and a recovery for every failure. *On stage:* Claude catching the cold joint. *Best fit:* the strongest Python developer.

| ID | Deliverable | Window | Done when |
|---|---|---|---|
| B1 | Repo, `contracts/`, root `CLAUDE.md` | Sat 11:00–12:00 | Everyone's Claude Code reads the contracts |
| B2 | MCP server: `fetch_part`, `look`, `inspect`, `show_footprint`, `mark_joint`, `speak`, `status` | Sat 12:00–16:00 | Every tool works against both robots |
| B3 | Board planner: pick-and-place + BOM → build plan (order, cups, polarity) | Sat 15:00–19:00 | Another board's files give a new plan with no code change |
| B4 | Vision checks: cup in handover zone; joint good, cold, bridged or missing | Sat 17:00–23:00 | 18 or more of 20 labelled photos correct |
| B5 | Recovery and speed: retry rules, spoken explanations, under 4 s thinking per step | Sat 23:00–Sun 04:00 | A run with one injected failure recovers alone |
| B6 | *Stretch:* assembly report written from the build log | Sun 04:00–06:00 | Report for one run |

## SCREEN · Experience

*Mission:* everything the audience sees and hears. *On stage:* the footprint lighting up on the live image of the real board. *Best fit:* front-end or design, good at demos.

| ID | Deliverable | Window | Done when |
|---|---|---|---|
| S1 | Bench screen live, wired to the MCP tools, every footprint checked against the real board | Sat 11:00–14:00 | `show_footprint` updates the monitor in under 0.5 s |
| S2 | Voice: push-to-talk (pedal or big key), local speech-to-text, spoken replies | Sat 13:00–18:00 | 10/10 commands understood in hall noise |
| S3 | AR overlay on the live camera image (homography from the four mounting holes) | Sat 18:00–Sun 02:00 | Highlight on the right pads for all five parts |
| S4 | Stage dashboard: screen, live camera, Claude's tool timeline, step status | Sun 06:00–10:00 | Followable with the sound off |
| S5 | *Stretch:* live 3D twin fed by Station joints | Sun 10:00–12:00 | Twin moves with the arm |

## BENCH · Product, hardware and story

*Mission:* the physical demo and why it matters. *On stage:* the live solder and the glove finale. *Best fit:* whoever built SOL-MIO.

| ID | Deliverable | Window | Done when |
|---|---|---|---|
| H1 | Boards (stage + 2 rehearsal), fixture, cups, handover zone, iron, 12 V, camera mounts | Sat 11:00–15:00 | Bench resets in under 2 minutes |
| H2 | Glove finale: finished SOL-MIO + glove + `LokmanPump`, on battery | Sat 15:00–20:00 | 10 inflations in a row |
| H3 | Reference photos: good, cold, bridged, missing joints through the wrist camera | Sat 16:00–19:00 | 20+ labelled photos in `board/photos` |
| H4 | Pitch and story: 3-minute script, slides, judge Q&A | Sat 20:00–Sun 06:00 | Two timed run-throughs under 3:00 |
| H5 | Rehearsal captain and submission: checkpoints, backup video, README, credits, form | Sun 10:00–17:45 | Submitted before 17:30 |

## Checkpoints (five minutes, all four people, at the bench)

| When | What must work |
|---|---|
| Sat 12:00 | Contracts frozen; repo and fake robot in |
| Sat 14:00 | Station reads joints and cameras; bench screen on the monitor; MCP tools visible in Claude Code |
| Sat 18:00 | One part end to end on the real arm |
| Sat 23:00 | All five parts plus inspection, timed |
| Sun 02:00 | AR overlay, planner and vision checks in |
| Sun 10:00 | Stage dashboard and pitch draft done |
| **Sun 12:00** | **Feature freeze, backup video recorded** |
| Sun 12:00–17:00 | Ten full rehearsals; fix only what breaks |
| Sun 17:45 | Submit |
| Sun 19:00 | Pitch |

## Sleep shifts

- ARM and SCREEN sleep Sun 02:00–06:00.
- BRAIN and BENCH sleep Sun 06:00–10:00.

Someone is always at the hardware.
