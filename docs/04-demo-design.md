# 04 · Demo design

> **Superseded on Sat 21 Nov 15:30 by [10 · Plan v2: the resistor picker](10-plan-resistor-picker.md).** Kept for reference.

## One line

**Soldering needs three hands. You have two.** Third Hand is the third: it fetches parts, shows where they go and checks your work, while you hold the iron and talk.

## Roles in the demo

| Who | Does |
|---|---|
| Person | Talks, places parts, solders. Hands never leave the work. |
| Claude | Plans the build, calls the tools, watches through the cameras, explains and recovers. |
| ElRobot arm | Fetches cups to the handover zone, moves the wrist camera for inspection. Never holds the iron. |
| Bench screen | Shows the board and lights up the footprint of the next part, with polarity hints. |

### Why the screen points, not the arm

The jaws are far wider than the 0603 resistor and the 1206 LED we place, so the arm cannot point at a footprint precisely and would cover it. The bench screen draws the SOL-MIO from its Altium data, dims everything except the target footprint, makes its pads glow, and shows the cup to take and the polarity rule. The arm then needs only about ten taught poses and no IK.

## The board: SOL-MIO v1.3

Our own controller board for a muscle-controlled pneumatic rehab glove (Altium project `Muscle_MB2`): 97 × 100 mm, ATmega2560, L298N, 7805, white solder mask with black silkscreen. For the demo we populate the **power stage** of a fresh board:

12 V → J2 → D2 → VIN (C4, C13) → U1 7805 → 5 V → R1 → D1 (power LED)

- **Fitted before the event** (through-hole, soldered from the underside): U1 (7805), J2 (DC jack).
- **Placed live** (SMD, smallest first): D2, R1, D1, C4, C13. Cups and details in `docs/08-bench-and-parts.md`.
- **End of the build:** 12 V into J2, D1 lights.
- **Finale:** the finished SOL-MIO (built earlier) drives the soft glove: flex a muscle, the glove inflates (`LokmanPump` firmware).

## Bench layout (robot frame, metres, robot faces +y, +x is its right)

| Item | Position |
|---|---|
| Robot base | (0, 0) |
| SOL-MIO on standoffs, turned 180° so the power corner faces the arm | centre (0.036, 0.187), board top at 27.6 mm |
| Parts tray, 2 × 3 cups | slots from (−0.175, 0.09) to (−0.095, 0.135) |
| Handover zone | (0.135, 0.15) |
| Iron stand | (0.19, 0.37), person's side |
| Side camera | (0.36, −0.02), 0.33 m high, looking at the work area |
| Bench screen | left of the robot, facing the person |

Taught poses: home, park (over the tray, clear of the iron), each cup above and at grip height, handover above and place, inspect over the power corner.

## Stage script (about 2 minutes)

1. "Soldering needs three hands. We have two." (15 s)
2. "Next part." The screen lights up D2; Claude says which cup and which way the band goes; the arm brings the cup.
3. Show self-correction once: the arm misses a cup, the side camera sees the empty handover zone, Claude says so and retries slower.
4. Solder two parts live. The rest of the stage board is pre-soldered (a full five-part build takes about three minutes in our simulation).
5. "Check my joints." The wrist camera finds a cold joint, the screen circles it, Claude tells you to reheat for three seconds. Reheat, check again: pass.
6. Plug in 12 V: D1 lights. Then the finished SOL-MIO drives the glove.
7. The pitch: what it is, how it works (Station, MCP, cameras, board data), why it matters (any board, every build logged as data), who needs it.

## Simulation

`sim/` replays this whole script in 3D with the real ElRobot model, the real SOL-MIO data and the bench screen. Use it to explain the plan to new teammates and to sanity-check the bench layout.
