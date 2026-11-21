# 10 · Plan v2: the resistor picker

**Status: the plan from Sat 21 Nov 15:30.** It replaces the SOL-MIO cup demo in docs 04, 05 and 08. Docs 01–03 (event, Station, June winner) and the safety rules in `CLAUDE.md` still hold.

Live team tracker with owners and status: https://claude.ai/artifact/DuCRQLU5JGacwz4uvjZpJj

## What changed and why

| Before | Now | Why |
|---|---|---|
| SOL-MIO power stage, SMD parts in cups | A simple Arduino Uno circuit on a breadboard; resistors plugged in live, no soldering | Fast to build live, easy for the audience to follow |
| Arm fetches a cup from a taught slot | Arm picks one resistor at a time | Picking the part itself is the robotics problem |
| Taught motions only | **SmolVLA fine-tuned on our own demos** does the grasp; a scripted grasp is the fallback | Uses NormaCore's own training stack, which is what the track judges care about |
| Cameras check cups and joints | **Claude reads the colour bands** of every resistor and picks the right one | Vision that has to be right, visible on screen |

## The demo in one line

You say which LED you are wiring. Claude works out the resistor, reads every resistor on the rack through the wrist camera, the arm picks the right one with a policy we trained on NormaCore's stack, and the screen shows where it goes on the perfboard.

## Stage script (about 3 minutes)

1. **You:** "Blue LED on pin 10. What resistor?"
   **Claude:** "5 minus 3.1 is 1.9 volts. At 13 mA that is 150 Ω: brown, green, brown." The screen shows the calculation.
2. **`scan_rack()`:** the wrist camera passes over the six slots. The screen fills in each value as Claude reads it.
3. **`pick(4)`:** the arm goes above slot 4, the VLA grasps the 150 Ω resistor, and the arm drops it in the dish by your hand. The screen shows the breadboard holes (b20 to b24).
4. You plug it into the breadboard. Repeat for the red LED (220 Ω: it drops less voltage, so it needs more resistance for the same brightness) and the button's pull-down (10 kΩ).
5. **Judge moment:** a judge swaps two resistors on the rack. Claude scans again and still picks the right one.
6. **Finale:** "Make them take turns when I press the button." Claude writes the sketch, uploads it with `arduino-cli` over USB, and checks through the table camera that both LEDs light.

## The bench

- **Circuit:** an Arduino Uno, powered over USB from the laptop (5 V, no battery), and a half-size breadboard with a red LED on D9, a blue LED on D10 and a push button on D2. The jumpers, LEDs and button are in place beforehand. Only the three resistors go in live, plugged in by hand: no soldering, no iron. Values, bands, currents and a draft hole layout are in [`board/led-circuit.json`](../board/led-circuit.json).

  | Part | Pin | Why | Value | Bands | Current |
  |---|---|---|---|---|---|
  | R2 | D10 → blue LED | (5 V − 3.1 V) / 13 mA | **150 Ω** | brown, green, brown | 12.7 mA |
  | R1 | D9 → red LED | (5 V − 2.0 V) / 13 mA | **220 Ω** | red, red, brown | 13.6 mA |
  | R3 | D2 → GND | pull-down: D2 reads LOW until the button is pressed | **10 kΩ** | brown, black, orange | 0.5 mA |

  - Every pin stays well under 20 mA, and 1/4 W resistors are plenty.
  - Claude's teaching line: both LEDs get the same brightness, but the blue one drops more voltage, so it needs the smaller resistor.
- **Resistor set on the rack:** 4-band carbon film resistors (beige body, high contrast), one per slot: 150, 220, 330, 470, 680 Ω and 10 kΩ. 330, 470 and 680 are distractors. No two values share their first two bands, so a misread third band cannot swap two of them. Keep 1 kΩ off the rack, because it differs from 10 kΩ only in the third band. Bring spares of each.
- **Parts for three boards (stage plus two rehearsals):**
  - 3 Arduino Uno (or clones) with USB-B cables
  - 3 half-size breadboards and a male-to-male jumper wire kit
  - 5 mm LEDs: 3 red, 3 blue, plus spares
  - 3 × 6 mm push buttons
  - 10 each of 150 Ω, 220 Ω and 10 kΩ
  - 5 each of 330, 470 and 680 Ω
  - `arduino-cli` installed on the bench laptop (board `arduino:avr:uno`), with a test sketch uploaded once. Clone Unos with a CH340 USB chip may need its driver
- **Rack ("ladder"):** two raised rails 12 mm apart on a white board. Each resistor lies across the rails, so its body hangs over the gap and its bands face up. Six slots, 30 mm apart, taped to the mat.
  - The jaws get tape or foam pads for grip.
  - If the jaws cannot hold a bare resistor, tape each one to a small card paddle and grip the paddle instead.
- **Light:** a diffuse light above the rack. No hard reflections on the bands.
- **Cameras:**
  - The table camera goes overhead, looking almost straight down (see the 3D simulation), so the arm never blocks it.
  - The wrist camera reads the bands from 5–8 cm above.
- **Handover:** a small dish next to the breadboard.

## The system

```
You (voice) → Claude Code → MCP server (thin) → Hub (FastAPI, owns Station + safety)
                                                   ├─ motion: taught poses, hover over a slot, handover
                                                   ├─ grasp: SmolVLA policy (fine-tuned)  |  scripted fallback
                                                   ├─ vision: resistor reader (wrist cam), table check
                                                   └─ events → bench screen
                                              Station :8888 ↔ ElRobot (follower) + leader arm + 2 cameras
```

**MCP tools Claude sees:**

| Tool | Does |
|---|---|
| `scan_rack()` | Wrist camera over every slot. Returns per slot: value, bands, confidence, thumbnail |
| `pick(slot)` | Hover → grasp (VLA, or scripted if the VLA is off or fails) → lift → check the grip → drop in the dish |
| `look(camera)` | Raw picture from the table or wrist camera, so Claude can see for itself |
| `show_step(led, value, holes)` | Bench screen: calculation, chosen resistor, where it goes |
| `speak(text)` | Spoken reply, also shown as a caption |
| `status()` | Robot state, last scan, faults |

There is still no free joint-move tool for the model. The VLA only runs inside `pick`, from a known hover pose, with Station's current limits and the policy runner's per-step limit (`--max-delta-ticks`).

**How the VLA fits in:**
- It is NormaCore's SmolVLA wrapper, `software/ai/smolvla_py`, with the base model `lerobot/smolvla_base` from Hugging Face.
- We fine-tune it on 50–60 demonstrations recorded with the leader arm. Each demonstration starts above a random slot and ends with the resistor lifted 5 cm. The language instruction is always "pick up the resistor below the gripper".
- Choosing *which* resistor is Claude's job; the policy only grasps.
- The wrapper was written for the SO-101 arm, so it has to be adapted to ElRobot's 7 joints plus jaws and our two cameras. NormaCore's staff have run SmolVLA fine-tunes on ElRobot before: ask them first.

**How the resistor reader works:**
- The Hub crops each slot from a wrist-camera frame.
- Claude classifies each crop against the six values on the rack (150 Ω … 10 kΩ), using a labelled reference photo of every value and structured output.
- Classifying against a known set is far more reliable than reading arbitrary bands.
- It is measured on 30 labelled photos before we rely on it.

## Team and tasks

Four roles, each owning a whole system. Put your name on one in the tracker.

### ROBOT · Robot and data (`R`)
*Owns on stage:* the arm picking the resistor and the drop into the dish.

| ID | Task | When | Done when |
|---|---|---|---|
| R1 | Station, calibration and leader teleop: follower and leader serials pinned, both arms calibrated, mirroring on and off from a script (`CT_START_MIRROR` / `CT_STOP_MIRROR`) | Sat 15:30–17:30 | The leader drives the follower smoothly; `elrobot.py` moves the follower with mirroring off |
| R2 | Rack and grip test (with BENCH): the ladder rack, jaw pads, 10 leader-arm grasps per slot | Sat 16:00–18:30 | 9 of 10 grasps hold, otherwise switch to paddles |
| R3 | Taught poses and the scripted pick: home, park, clear, scan and hover pose per slot, handover; `pick(slot)` without the VLA | Sat 18:30–20:00 | Scripted pick works 9 of 10 times on every slot |
| R4 | Record grasp demos (with VLA): 60 leader-arm episodes from the hover pose, resistors shuffled, small offsets, each tagged in Station | Sat 20:00–22:00 | 60 good episodes tagged and handed to VLA |
| R5 | Safety and reliability (with AGENT after 01:00): e-stop key, hands zone (the arm parks while hands are on the breadboard), 30 unattended scripted picks with a log | Sat 22:00–Sun 03:00 | 27 or more of 30 succeed |
| R6 | Stage grasp: the grasp that wins at 07:00 goes into `pick(slot)`, then 20 picks again | Sun 07:00–10:00 | 18 or more of 20 with the stage setup |

Sleeps Sun 03:00–07:00.

### VLA · Fine-tuning (`V`)
*Owns on stage:* "we trained this grasp last night on NormaCore's stack".

| ID | Task | When | Done when |
|---|---|---|---|
| V1 | SmolVLA pipeline on ElRobot: install `smolvla_py`, adapt it from SO-101 (8 motors, table and wrist cameras), get Nebius access from NormaCore | Sat 15:30–19:00 | A 200-step run on 5 test demos finishes and `run_policy.py` loads the checkpoint |
| V2 | Policy grasp skill in the Hub: `policy_grasp(timeout=8 s)` runs the policy at about 10 Hz from the hover pose, stops on closed jaws, timeout or e-stop | Sat 19:00–20:00 | A dummy policy runs through the Hub with the safety limits |
| V3 | Dataset export: Station recordings → training set, joints and frames aligned, 224 px images, one instruction. Build it on the first 5 demos while R4 records the rest | Sat 20:00–22:30 | R4's episodes uploaded and checked by eye |
| V4 | Fine-tune on Nebius: about 10k steps on an L40S (NormaCore's example uses batch 64), checkpoints every 2k; launched by 22:30 | Sat 22:30–Sun 03:00 | Final checkpoint downloaded |
| V5 | Evaluate and tune on the arm (BENCH at the power switch): 20 policy grasps across slots, action chunk size and speed | Sun 03:00–07:00 | 16 or more of 20 means the VLA goes on stage; otherwise the scripted grasp does. Decision at 07:00 |

Sleeps Sat 23:00–Sun 03:00 while training runs.

Everything for V1–V5 is in [`vla/`](../vla/README.md): setup, recording rules, export and dataset check, an ElRobot trainer (8 joints, not upstream's fixed 6), the Nebius submit and fetch scripts, and `policy_grasp.py` with its tests. It is tested end to end without the arm, but not yet on the arm or on a Nebius GPU.

### AGENT · Claude and vision (`C`)
*Owns on stage:* Claude reading the rack and catching the swapped resistors.

| ID | Task | When | Done when |
|---|---|---|---|
| C1 | Hub and MCP tools on a fake robot: `scan_rack`, `pick`, `look`, `show_step`, `speak`, `status`; the Hub keeps Station, the motion lock and the e-stop | Sat 15:30–19:00 | Claude Code runs a whole fake build |
| C2 | Resistor reader: wrist-camera crops, few-shot classification against the known set, eval script | Sat 19:00–23:00 | 28 or more of 30 labelled photos right, under 3 s per resistor |
| C3 | Demo agent instructions: work out R from LED colour and supply, say it, scan, pick, guide, verify; short spoken lines; retry rules | Sat 23:00–Sun 01:00 | A fake run reads naturally from start to finish |
| C4 | Real-arm integration (with ROBOT): replace the fake robot with Station, using the scripted grasp | Sun 01:00–03:00 | The whole demo runs once on the real arm |
| C5 | Recovery and speed: a judge swaps resistors, a grasp misses, a scan is unsure; three full runs | Sun 07:00–11:00 | A run with a swap and a missed grasp recovers by itself |

Sleeps Sun 03:00–07:00.

### BENCH · Circuit, screen and story (`P`)
*Owns on stage:* the live build and the pitch.

| ID | Task | When | Done when |
|---|---|---|---|
| P1 | Circuit and parts: the Uno and breadboard with jumpers, two LEDs and the button in place, the resistor set, one finished reference board, `arduino-cli` uploading from the laptop; fix the hole positions in `board/led-circuit.json` to match the real board | Sat 15:30–17:00 | The reference board runs a test sketch uploaded from the laptop; `board/led-circuit.json` matches the real board and is handed to AGENT |
| P2 | Rack, light and bench (with ROBOT): white board, diffuse light, overhead table camera, dish, a 2-minute reset | Sat 16:00–18:30 | The bench resets in under 2 minutes |
| P3 | Reference photos for the reader: 30+ wrist-camera photos of each value on the rack, labelled | Sat 18:30–20:00 | Labelled set in `board/photos/resistors/`, handed to AGENT |
| P4 | Bench screen: rack as Claude reads it (crop, bands, value, confidence), the LED calculation, the breadboard with the next holes lit | Sat 20:00–23:00 | Updates live from `scan_rack` and `show_step` |
| P5 | Voice: macOS dictation into Claude Code, `say` for replies, a push-to-talk key | Sun 03:00–04:00 | 10 of 10 commands understood |
| P6 | Pitch: 3-minute script, slides, judge Q&A (why Claude plus a VLA, NormaCore's data flywheel); at the power switch during V5 | Sun 04:00–08:00 | Two timed run-throughs |
| P7 | Rehearsal captain and submission: ten rehearsals, backup video by 12:00, README and credits, the form | Sun 08:00–17:45 | Submitted before 17:30 |

Sleeps Sat 23:00–Sun 03:00.

## Checkpoints (five minutes, everyone at the bench)

| When | What must work |
|---|---|
| Sat 17:30 | The leader drives the follower; the rack is built; the jaws hold a resistor |
| Sat 19:00 | Claude Code runs a fake build; SmolVLA trains on 5 test demos |
| Sat 22:30 | 60 demos recorded, training launched; scripted pick works; reader first eval |
| Sun 03:00 | The whole demo runs on the real arm with the scripted grasp; reader 28/30; bench screen live; checkpoint downloaded |
| Sun 07:00 | **VLA decision:** the policy or the scripted grasp goes on stage |
| Sun 10:00 | Three clean full runs with the stage grasp; pitch draft |
| **Sun 12:00** | **Feature freeze, backup video recorded** |
| Sun 17:45 | Submit |
| Sun 19:00 | Pitch |

Two sleep shifts, so two people are always at the hardware:

- Sat 23:00–Sun 03:00: VLA and BENCH sleep (training runs); ROBOT and AGENT bring the demo up on the real arm.
- Sun 03:00–07:00: ROBOT and AGENT sleep; VLA tests the policy with BENCH at the power switch.

## Fallbacks

| If | Then |
|---|---|
| No Nebius GPU or training fails | Scripted grasp on stage. The story becomes "every grasp is recorded as training data in Station", with the demos and the dataset shown |
| The VLA works on fewer than 16 of 20 | Scripted grasp on stage; the VLA shown in the backup video |
| The jaws cannot hold a bare resistor | Card paddles |
| The reader gets fewer than 28 of 30 right | Fewer values with very different bands; Claude takes a second photo when unsure |
| A grasp misses on stage | `pick` checks the grip; Claude says so and retries |
| Voice fails | Type the same sentence into Claude Code |

## What we keep from before

- `robot/normacore/`: Station setup and `elrobot.py`.
- The Hub design and safety layers in doc 09. Its tools change to the table above.
- The bench screen code, as a starting point for P4.
- The 3D simulation. Its "Cup moved" scenario shows the same perception loop with cups.
