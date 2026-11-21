# servo_sim: STS3215 acceleration/speed settings in simulation

MuJoCo model of the ElRobot (URDF masses from `sim/`, +30 g cup, gravity) with a model of each
STS3215 servo: firmware speed/acc ramp, P-D position loop on 4096-tick encoder, 2.94 N·m / 4.71 rad/s
motor line, reflected rotor inertia, gear friction. Uncertain internals (gain, rotor inertia, real
55 g servo mass) are swept as variants; the ranking of settings is the same in all of them.

```bash
python3 -m venv .venv && .venv/bin/pip install mujoco numpy
python3 extract_urdf.py
.venv/bin/python servo_sim.py elrobot.urdf results.json     # ~1 min
```

Result (speed 600, time until the joint visibly moves, peak torque):

| acc | wrist j7 | elbow j3 | shoulder j2 |
|---|---|---|---|
| 20 (old) | 90 ms, 4 % | 94 ms, 23 % | 99 ms, 36 % |
| 50 | 64 ms, 6 % | 68 ms, 27 % | 73 ms, 43 % |
| 100 | 51 ms, 8 % | 54 ms, 32 % | 58 ms, 50 % |
| 150 | 44 ms, 11 % | 47 ms, 34 % | 52 ms, 52 % |
| 0 (no ramp) | 27 ms, 14 % | 30 ms, 36 % | 34 ms, 53 % |

acc 20 reproduces the ~90 ms lag measured on the real arm. Speed changes only the total move
time, not the start. elrobot.py's 0.04-per-0.12 s stepping does not lower peak torque (the
servo ramp already limits it) and adds ~100 ms on short jaw moves. Not modelled: Station and
network delay, the servo's own overload logic, backlash.

## Characters (`../character.py`)

`sim_character.py` plays every character × gesture (and 8 s of idle) on this model with real
55 g servos, the arm reaching forward. Findings that set the caps in `character.py`:

- A sudden "startle" with the elbow at acc 100 put the shoulder at 87–98 % of stall (overload trip).
  The load is mostly the elbow's reaction. Elbow cap 40 and shoulder cap 30 bring every character to
  ≤ 65 % (holding the pose alone is ~38 %).
- The trickster at 0.25 s per beat reached only 30 % of each move before the next began; 0.4 s gives 77 %
  (deliberately blended). All other characters reach ~100 %.

```bash
.venv/bin/python sim_character.py
```
- **smooth** follows minimum-jerk curves sampled at 20 Hz instead of jumping between poses. Tuned to
  servo acc × 0.35 and 0.65 s per beat: peak joint acceleration 7–9 rad/s² (butler ~30, trickster ~45,
  sleepy ~10) at full movement size, shoulder ≤ 47 %. The arm trails the curve by 2–6° (13° on the quick
  curious tilt). Its "moves reached" number in sim_character.py is low by design: each 50 ms step is a
  tiny slice of a moving curve.

## Viewer (`viewer/`)

`export_animation.py viewer/anim.json` simulates every character × gesture from an upright standing
pose and saves the joint motion the servos actually produce. `viewer/index.html` plays three
characters side by side on the real ElRobot model (shoulder peak from standing ≤ 35 %).

```bash
cd robot/normacore/servo_sim/viewer && python3 -m http.server 8090    # open http://localhost:8090
```

### Prompts in the viewer

Type a moment ("taste something sour") and Claude writes one choreography (keyframes in the
`GESTURES` format); `viewer/engine.js` plans it the way `character.py` does for each character and
plays it on a light servo model (the STS3215 speed/acc ramp plus a 10 ms lag). Checked against the
physics clips with `node viewer/test_engine.mjs`: mean joint difference 0.36°. Prompt clips are not
physics-checked for torque; "Copy as Python gesture" gives a `GESTURES` entry to run through
`sim_character.py` before the real arm. Prompts work only inside claude.ai (the `sample` capability).

### Scenes with props

`character.SCENES` adds 15 little stories (kick a ball, put on a hat, air kiss, catch a ball, smell a
flower, scared by a spider, sneeze, nod off, …). Each `Step` now carries the keyframe it starts, and
the exporter saves those times per clip, so the viewer's props (ball on a tee, bowler hat, heart,
flower, thrown ball, spider) happen at each character's own moment. Physics check: from the reaching
pose every scene stays ≤ 71 % of shoulder stall after softening the kick and hat flick and capping
j4 at 80 and j6 at 150 (they whip and push the shoulder); from standing ≤ 42 %.
`viewer/pick.js` (wave to you, pick up the smallest) came from a parallel session and is kept as is.
