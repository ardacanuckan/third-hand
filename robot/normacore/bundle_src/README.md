# Third Hand characters

Expressive personalities for an 8-servo robot arm (built on the ElRobot with Feetech STS3215 servos).
Ten characters can each perform 9 gestures and 15 short scenes in their own style: the same "kick a ball" looks
bouncy from the trickster, heavy from the grump, and gliding from smooth.

Nothing here depends on a particular robot stack. You get:

| Path | What it is | Needs |
|---|---|---|
| `characters.json` | All data: characters, gestures, scenes, prop timing, joint meanings, units, safety limits | nothing |
| `python/thc/` | Planner and player: turns (character, move) into timed joint goals and plays them through your `send()` | Python 3.9+, standard library |
| `js/thc.js` | Same planner plus a servo model that outputs joint angles (radians) at 30 fps | any JS runtime |
| `trajectories.json` | 250 ready-made clips: joint angles (rad, 30 fps) from a physics simulation | nothing |

## Quick start

```bash
cd python
python3 examples/play_fake_robot.py --list
python3 examples/play_fake_robot.py trickster kick_ball      # prints every command it would send
python3 -m unittest discover tests                            # self-check
node ../js/example.mjs smooth air_kiss                        # JavaScript version
```

## Two ways to integrate

**A. Your robot accepts per-joint acceleration and speed (STS3215 or similar).** Use the planner and write one
function:

```python
from thc import Library, play
lib = Library.load()

def send(goals, acc, speed):
    # goals: {"j1": 0..1, ...} normalized positions; acc / speed: STS3215 register units per joint
    ...

play(lib.plan("trickster", "kick_ball", neutral=my_neutral_pose), send, read=my_read_positions)
```

`examples/sts3215_template.py` shows the register writes. `thc.units` converts to rad, rad/s and rad/s² for
other servos. `read()` is optional. With it, "bound" characters really wait for their joints to arrive. Without
it, the player waits an estimated move time.

**B. Your robot only takes position targets.** Stream a pre-computed clip:

```python
from thc import trajectories
for t, q in trajectories.frames("smooth/air_kiss"):   # q = {"j1": rad, ..., "j8": rad}, 30 fps
    robot.set_joint_angles(q)                          # at time t
```

The clips start and end in the standing pose `stand_rad` (in the file). They show what the STS3215 servos
actually produced in simulation, so the character's acceleration and overshoot are already baked in.

## The body

| Joint | ElRobot part | Acts as |
|---|---|---|
| j1 | base yaw | turning, looking left/right |
| j2 | shoulder pitch | leaning forward (+) / back (−) |
| j3 | elbow pitch | neck height (+ droops) |
| j4 | pitch | neck bend (+ head down) |
| j5 | roll | body twist |
| j6 | wrist pitch | nod (+ down) |
| j7 | wrist roll | head tilt |
| j8 | gripper jaws | mouth (+ opens) |

If your arm differs, map these meanings onto your joints. A joint that moves the wrong way after calibration is
flipped with `limits.sign` in `characters.json`.

## Units

- **Positions** are normalized 0..1 inside each joint's calibrated range (NormaCore Station's `position_norm`).
  Every move is a small offset from a **neutral pose** you pass in. Teach one with the arm upright and clear. The
  default is 0.5 for every joint.
- **Gesture offsets** in `characters.json` are in units of 6 % of a joint's range. **Beats** × the character's
  `tempo` = seconds.
- **acc**: STS3215 register 0x29, 100 ticks/s² per unit. **speed**: register 0x2E, ticks/s. 4096 ticks = one turn.

## The characters

| Name | Based on | Moves |
|---|---|---|
| curious | high openness | quick head tilts, leans in, glances |
| shy | introvert | small, slow, leans back, slight tremor |
| braggart | Il Capitano (commedia dell'arte) | big, sudden, holds poses |
| grump | Pantalone | heavy, slow, stops dead |
| trickster | Arlecchino | bouncy, winds up, overshoots |
| sleepy | low energy | very slow, sagging, deep breathing |
| nervous | anxious | quick, small, jittery |
| sage | calm mentor | slow, smooth, deliberate |
| smooth | Laban glide/float | follows minimum-jerk curves, never stops mid-gesture |
| butler | polite assistant | quick and precise, then perfectly still |

Each one is a handful of numbers (acceleration and speed multipliers, size, tempo, flow, anticipation,
overshoot, tremor, posture, breathing). Add your own by copying an entry in `characters.json`.

**Moves.** Gestures: yes, no, hello, curious, look around, startle, sigh, laugh, sulk. Scenes: wave hello, kick
a ball, put on a hat, air kiss, bow, dance, sneeze, yawn & stretch, peekaboo, smell a flower, catch a ball,
think, celebrate, nod off, scared. You can also pass your own keyframes: `[[beats, {"j6": 1.0}], ...]`.

**Props.** Scenes like kick a ball or put on a hat imagine objects. `props` in `characters.json` names the
keyframe where each one is touched. Every planned step carries `key` (the keyframe it starts), and
`trajectories.json` lists those times per clip, so you can sync real or animated props.

## Safety (please keep)

- `limits` cap every joint's distance from neutral and its acceleration. The shoulder and elbow are never
  sudden, because fast moves there overloaded the shoulder in simulation.
- Simulation results with real 55 g servos: the hardest move uses at most 42 % of the shoulder's stall torque
  from the standing pose, and 71 % with the arm stretched forward. Start from an upright neutral pose.
- Joint directions depend on calibration. Run the first moves slowly with a hand on the power switch and away
  from people.

## Where it comes from

Third Hand, AI × Robotics Hackathon II (Berlin, November 2026), NormaCore track. Character design draws on
Laban Movement Analysis, commedia dell'arte stock characters and the Big Five personality traits. Timing and
caps were checked in a MuJoCo model of the ElRobot with an STS3215 firmware model.
