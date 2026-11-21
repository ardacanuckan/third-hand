"""Expressive characters for the 8-servo ElRobot: the same gesture, performed by different personalities.

A personality is a set of motion qualities (Laban Movement Analysis: Time, Weight, Space, Flow),
turned into STS3215 settings: acceleration (sudden vs sustained), speed, size of movement,
tempo, flow (blend keyframes or stop at each), anticipation, overshoot, tremor, posture
and idle behaviour (breathing, glances).

    from character import PERSONALITIES, GESTURES, plan
    steps = plan(PERSONALITIES["trickster"], "yes")      # pure: no robot needed

    await perform(arm, "trickster", "yes")                # on the real arm (from a neutral pose)
    await idle(arm, "sleepy", seconds=10)

How the joints read as a body (axes from the ElRobot URDF):
    j1 base yaw   -> turn the whole body / look left-right / head shake
    j2 shoulder   -> lean forward/back (posture). Kept gentle: it carries the arm.
    j3 elbow      -> neck height: proud and tall vs drooping
    j4 pitch      -> neck bend
    j5 roll       -> body twist / tilt
    j6 pitch      -> head nod (wrist pitch)
    j7 roll       -> head tilt (the curious dog tilt)
    j8 jaws       -> mouth / beak

Signs of each joint depend on calibration. If a gesture goes the wrong way on your arm, flip it
in SIGN. Everything is a small offset (at most MAX_DEV) from the "neutral" pose.
"""
from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass, field

JOINTS = ("j1", "j2", "j3", "j4", "j5", "j6", "j7", "j8")
SIGN = {j: 1.0 for j in JOINTS}            # flip to -1.0 where a joint moves the wrong way
MAX_DEV = {"j1": 0.15, "j2": 0.05, "j3": 0.12, "j4": 0.12, "j5": 0.12, "j6": 0.15, "j7": 0.15, "j8": 0.25}

# Base motion profile (same as elrobot.JOINT_PROFILE) and hard caps. Caps from servo_sim/sim_character.py:
# with the shoulder at acc 50 and the elbow at 100, a sudden "startle" reached 87-98 % of the shoulder's
# stall torque (overload trip). Most of it is the elbow's reaction, not the shoulder's own motion:
# elbow cap 40 -> worst case 69 % (holding the reaching pose alone is ~38 %). The shoulder and elbow are
# never sudden, whatever the character: personality lives in the wrist, base turn and jaws.
# The scenes (kick, hat flick) showed the neck (j4) and wrist pitch (j6) also push the shoulder when
# they whip: caps 80 and 150 take the trickster's kick from 92 % to ~80 % in the reaching pose.
BASE = {"j1": (40, 600), "j2": (30, 600), "j3": (60, 700), "j4": (100, 800),
        "j5": (150, 900), "j6": (150, 900), "j7": (150, 900), "j8": (150, 900)}
ACC_CAP = {"j1": 80, "j2": 30, "j3": 40, "j4": 80, "j5": 254, "j6": 150, "j7": 254, "j8": 254}
SPEED_CAP = {"j1": 900, "j2": 700, "j3": 1000, "j4": 1500, "j5": 2000, "j6": 2000, "j7": 2000, "j8": 2000}


@dataclass(frozen=True)
class Personality:
    name: str
    archetype: str            # where the type comes from
    laban: str                # Time / Weight / Space / Flow
    acc: float                # multiplier on the base acceleration (sudden > 1, sustained < 1)
    speed: float              # multiplier on the base speed
    size: float               # multiplier on gesture amplitude
    tempo: float              # seconds per beat
    blend: float              # 0 = wait for each pose (bound flow) .. 0.7 = next pose starts early (free flow)
    anticipation: float       # small opposite move before a big one (fraction of the move)
    overshoot: float          # go past the target, then settle (fraction of the move)
    tremor: float             # random jitter on the head joints (norm)
    posture: dict = field(default_factory=dict)   # standing offsets from neutral
    breath: float = 0.01      # idle breathing amplitude on j3/j6
    breath_s: float = 4.0     # breathing period
    glance_s: float = 0.0     # mean seconds between idle glances (0 = never)
    smooth: bool = False      # follow a continuous minimum-jerk curve at 20 Hz instead of jumping between poses


PERSONALITIES: dict[str, Personality] = {p.name: p for p in [
    Personality("curious", "high Openness; the inquisitive pet", "sudden / light / indirect / free",
                acc=1.6, speed=1.3, size=1.0, tempo=0.45, blend=0.4, anticipation=0.0, overshoot=0.10,
                tremor=0.0, posture={"j2": 0.02, "j6": -0.03, "j7": 0.04}, breath=0.008, breath_s=3.0, glance_s=2.5),
    Personality("shy", "introvert, high Neuroticism", "sustained / light / indirect / bound",
                acc=0.5, speed=0.6, size=0.5, tempo=0.6, blend=0.0, anticipation=0.15, overshoot=0.0,
                tremor=0.003, posture={"j2": -0.03, "j3": 0.04, "j6": 0.05, "j1": 0.05}, breath=0.006, breath_s=3.5, glance_s=5.0),
    Personality("braggart", "Il Capitano (commedia): the show-off", "sudden / strong / direct / bound",
                acc=1.4, speed=1.3, size=1.5, tempo=0.5, blend=0.0, anticipation=0.20, overshoot=0.0,
                tremor=0.0, posture={"j2": -0.02, "j3": -0.06, "j6": -0.05}, breath=0.015, breath_s=5.0, glance_s=0.0),
    Personality("grump", "Pantalone (commedia): the grumbling old miser", "sudden stops / strong / direct / bound",
                acc=0.8, speed=0.6, size=0.8, tempo=0.8, blend=0.0, anticipation=0.0, overshoot=0.0,
                tremor=0.002, posture={"j2": 0.02, "j3": 0.05, "j6": 0.06, "j7": -0.02}, breath=0.012, breath_s=6.0, glance_s=8.0),
    Personality("trickster", "Arlecchino (commedia): the bouncy joker", "sudden / light / indirect / free",
                acc=2.0, speed=1.6, size=1.2, tempo=0.4, blend=0.35, anticipation=0.25, overshoot=0.25,
                tremor=0.0, posture={"j7": -0.05, "j6": -0.02}, breath=0.01, breath_s=2.0, glance_s=1.5),
    Personality("sleepy", "low arousal; the dozing grandparent", "sustained / heavy / indirect / free",
                acc=0.3, speed=0.4, size=0.7, tempo=1.4, blend=0.7, anticipation=0.0, overshoot=0.0,
                tremor=0.0, posture={"j3": 0.07, "j6": 0.08, "j7": 0.04}, breath=0.02, breath_s=7.0, glance_s=0.0),
    Personality("nervous", "high Neuroticism; the anxious type", "sudden / light / indirect / bound",
                acc=1.8, speed=1.2, size=0.6, tempo=0.3, blend=0.2, anticipation=0.0, overshoot=0.05,
                tremor=0.008, posture={"j2": -0.02, "j3": 0.03, "j6": 0.03}, breath=0.01, breath_s=1.6, glance_s=1.0),
    Personality("sage", "high Conscientiousness; the calm mentor", "sustained / strong / direct / free",
                acc=0.6, speed=0.7, size=0.9, tempo=0.9, blend=0.5, anticipation=0.05, overshoot=0.0,
                tremor=0.0, posture={"j3": -0.02}, breath=0.01, breath_s=6.0, glance_s=0.0),
    Personality("smooth", "Laban's glide/float; the dancer, tai chi", "sustained / light / indirect / free",
                acc=0.35, speed=1.2, size=1.0, tempo=0.65, blend=0.0, anticipation=0.0, overshoot=0.0,
                tremor=0.0, posture={"j6": -0.01}, breath=0.012, breath_s=6.0, glance_s=0.0, smooth=True),
    Personality("butler", "the polite assistant; precise and efficient", "sudden-then-still / light / direct / bound",
                acc=1.2, speed=1.0, size=0.7, tempo=0.45, blend=0.0, anticipation=0.0, overshoot=0.0,
                tremor=0.0, posture={"j3": -0.03, "j6": -0.01}, breath=0.004, breath_s=5.0, glance_s=0.0),
]}

# Gestures: (beats, {joint: offset}) keyframes in units of about 0.06 norm, relative to the posture.
# A keyframe lists only the joints that change; the others keep their last value.
U = 0.06
GESTURES: dict[str, list[tuple[float, dict[str, float]]]] = {
    "yes":         [(1, {"j6": 0.8}), (1, {"j6": -0.3}), (1, {"j6": 0.8}), (1.5, {"j6": 0})],
    "no":          [(1, {"j1": 0.7}), (1, {"j1": -0.7}), (1, {"j1": 0.6}), (1.5, {"j1": 0})],
    "hello":       [(1, {"j3": -0.6, "j6": -0.5}), (0.5, {"j8": 1.5}), (0.5, {"j8": 0}),
                    (1, {"j6": 0.5}), (1, {"j6": -0.5}), (1.5, {"j3": 0, "j6": 0})],
    "curious":     [(1, {"j2": 0.6, "j6": -0.3}), (1.5, {"j7": 1.2}), (1, {"j7": -0.6}), (1.5, {"j7": 1.0}),
                    (2, {"j2": 0, "j6": 0, "j7": 0})],
    "look_around": [(1.5, {"j1": 1.2, "j6": -0.3}), (1, {}), (2, {"j1": -1.2}), (1, {}), (1.5, {"j1": 0, "j6": 0})],
    "startle":     [(0.4, {"j2": -0.4, "j3": -0.6, "j6": -1.0, "j8": 2.5}), (2, {}),
                    (2, {"j2": 0, "j3": 0, "j6": 0, "j8": 0})],
    "sigh":        [(1, {"j3": -0.4, "j6": -0.3}), (2, {"j3": 0.9, "j6": 1.0}), (1.5, {}),
                    (2, {"j3": 0, "j6": 0})],
    "laugh":       [(0.5, {"j6": -0.6, "j8": 1.2}), (0.4, {"j8": 0.2, "j6": -0.2}), (0.4, {"j8": 1.2, "j6": -0.6}),
                    (0.4, {"j8": 0.2, "j6": -0.2}), (0.4, {"j8": 1.2, "j6": -0.6}), (1.5, {"j8": 0, "j6": 0})],
    "sulk":        [(2, {"j1": -1.4, "j3": 0.8, "j6": 1.0}), (3, {}), (2, {"j1": 0, "j3": 0, "j6": 0})],
}

# Scenes: little stories with a beginning and an end. Same keyframe format as GESTURES.
# The "head" is the gripper and the jaws are its mouth, like a desk lamp with a beak.
SCENES: dict[str, list[tuple[float, dict[str, float]]]] = {
    "wave_hello":   [(1, {"j3": -1, "j6": -1.2, "j8": 1.5}),
                     (0.6, {"j5": 1.5, "j7": 1.5}), (0.6, {"j5": -1.5, "j7": -1.5}),
                     (0.6, {"j5": 1.5, "j7": 1.5}), (0.6, {"j5": -1.5, "j7": -1.5}),
                     (1, {"j5": 0, "j7": 0, "j8": 0}), (1.5, {"j3": 0, "j6": 0})],
    "kick_ball":    [(1, {"j6": 1.2}),                                        # look at the ball
                     (1, {"j2": -0.3, "j3": -1, "j4": -1.2, "j6": -0.5}),     # wind up
                     (0.4, {"j2": 0.1, "j3": 0.5, "j4": 1.6, "j6": 2.2}),     # swing: neck and wrist do the kick
                     (0.5, {"j4": 0.5, "j6": -1}),                            # contact, follow through
                     (1.5, {"j6": -1.5, "j3": -0.5}),                         # watch it fly
                     (0.4, {"j8": 2.5}), (0.3, {"j8": 0}), (0.3, {"j8": 2.5}), (0.3, {"j8": 0}),
                     (1.5, {"j2": 0, "j3": 0, "j4": 0, "j6": 0})],
    "put_on_hat":   [(1, {"j2": 0.4, "j3": 1.2, "j4": 0.3, "j6": 2}),        # look down at the hat
                     (0.6, {"j8": 3}), (0.6, {"j4": 1}),                      # open wide, reach
                     (0.5, {"j8": 0.5}),                                      # bite the brim
                     (1, {"j2": 0, "j3": 0, "j4": -1, "j6": 0}),              # lift it
                     (0.5, {"j6": 2.2, "j3": 0.8}),                           # dip
                     (0.35, {"j6": -2.5, "j3": -0.8, "j8": 3}),               # flick it up (wrist, not shoulder)
                     (1, {"j6": 0.3, "j3": -0.5, "j8": 0}),                   # head under it
                     (1.5, {"j3": -1.2, "j6": -0.5}),                         # proud
                     (1, {"j7": 1}), (1, {"j7": 0}),
                     (1.5, {"j2": 0, "j3": 0, "j4": 0, "j6": 0})],
    "air_kiss":     [(1, {"j3": -0.5, "j6": -0.5, "j8": 0}),
                     (1, {"j2": 0.35, "j4": 0.6, "j7": 1}),                   # lean in, pucker
                     (0.3, {"j8": 2.5, "j6": -1}),                            # mwah
                     (0.5, {"j8": 0}),
                     (1.5, {"j2": -0.4, "j7": -1.2, "j6": 0.8}),              # shy, looks away
                     (1.5, {"j2": 0, "j3": 0, "j6": 0, "j7": 0})],
    "bow":          [(1, {"j3": -0.8}), (1.5, {"j2": 0.8, "j3": 1.5, "j6": 2}), (1.5, {}),
                     (1.5, {"j2": 0, "j3": 0, "j6": 0})],
    "dance":        [(0.5, {"j1": 1, "j6": 0.8, "j5": 0.8}), (0.5, {"j1": -1, "j6": -0.3, "j5": -0.8}),
                     (0.5, {"j1": 1, "j6": 0.8, "j5": 0.8}), (0.5, {"j1": -1, "j6": -0.3, "j5": -0.8}),
                     (0.5, {"j3": -1, "j7": 1.5, "j8": 2}), (0.5, {"j3": 0, "j7": -1.5, "j8": 0}),
                     (0.5, {"j3": -1, "j7": 1.5, "j8": 2}), (0.5, {"j3": 0, "j7": -1.5, "j8": 0}),
                     (1.5, {"j1": 0, "j5": 0, "j6": 0, "j7": 0})],
    "sneeze":       [(0.8, {"j6": -1, "j8": 1}), (0.8, {"j6": -1.6, "j8": 1.8}),
                     (0.9, {"j6": -2.2, "j3": -0.8, "j8": 2.6}), (0.5, {}),
                     (0.25, {"j6": 2.2, "j3": 0.9, "j2": 0.3, "j8": 0.5}),    # achoo
                     (1, {}), (0.4, {"j1": 0.6}), (0.4, {"j1": -0.6}),
                     (1.5, {"j1": 0, "j2": 0, "j3": 0, "j6": 0, "j8": 0})],
    "yawn_stretch": [(2, {"j3": -1.6, "j6": -2, "j8": 4}), (1.5, {"j5": 1.5, "j7": 1}),
                     (1.5, {"j5": -1.5, "j7": -1}), (1, {"j5": 0, "j7": 0, "j8": 0}),
                     (2, {"j3": 0.5, "j6": 0.8}), (1.5, {"j3": 0, "j6": 0})],
    "peekaboo":     [(1.5, {"j1": 2.2, "j3": 1.5, "j6": 2}), (2, {}),          # hide
                     (0.35, {"j1": 0, "j3": -1.5, "j6": -1.5, "j8": 3.5}),    # boo
                     (0.4, {"j8": 0}), (0.3, {"j8": 3}), (0.4, {"j8": 0}),
                     (1.5, {"j3": 0, "j6": 0})],
    "sniff_flower": [(1, {"j6": 1}), (1.5, {"j2": 0.4, "j3": 1.2, "j6": 1.8}),
                     (0.3, {"j6": 2.1}), (0.3, {"j6": 1.8}), (0.3, {"j6": 2.1}), (0.3, {"j6": 1.8}),
                     (1.5, {"j2": -0.3, "j3": -1, "j6": -1.2, "j7": 1}),       # ahh
                     (1, {"j7": -1}), (1, {"j7": 1}), (1.5, {"j2": 0, "j3": 0, "j6": 0, "j7": 0})],
    "catch_ball":   [(1, {"j1": -1.5, "j6": -0.5}),                           # spots the throw
                     (1, {"j1": -0.5, "j6": -1.2, "j8": 3}),                  # tracks it, mouth open
                     (0.6, {"j1": 0.3, "j6": -0.8}),                          # catch
                     (0.4, {"j8": 1.2}),                                      # chomp
                     (1, {"j3": -1, "j6": -1.3}),                             # proud
                     (0.5, {"j5": 1}), (0.5, {"j5": -1}),
                     (1.5, {"j1": 0, "j3": 0, "j5": 0, "j6": 0})],
    "think":        [(1.5, {"j6": -1.2, "j7": 1.2}), (1.5, {"j1": 1, "j6": -1.5}), (1.5, {"j1": -0.5}), (1, {}),
                     (0.3, {"j3": -1, "j6": -0.5, "j7": 0, "j8": 2.5}),       # aha
                     (0.6, {"j6": 0.6}), (0.6, {"j6": -0.4}),
                     (1.5, {"j1": 0, "j3": 0, "j6": 0, "j8": 0})],
    "celebrate":    [(0.4, {"j3": -1.5, "j6": -1.5, "j8": 3}), (0.3, {"j3": -0.8, "j8": 1}),
                     (0.3, {"j3": -1.5, "j8": 3}), (0.3, {"j3": -0.8, "j8": 1}), (0.3, {"j3": -1.5, "j8": 3}),
                     (0.6, {"j1": 1.5, "j5": 1}), (0.6, {"j1": -1.5, "j5": -1}),
                     (1.5, {"j1": 0, "j3": 0, "j5": 0, "j6": 0, "j8": 0})],
    "nod_off":      [(2, {"j3": 0.8, "j6": 1}), (2, {"j3": 1.5, "j6": 2, "j8": 1}),
                     (0.2, {"j3": -0.5, "j6": -0.8, "j8": 0}),                # jolts awake
                     (1, {"j1": 0.6}), (1, {"j1": -0.6}), (1.5, {"j1": 0, "j3": 0, "j6": 0})],
    "scared":       [(1, {"j6": 1.5}),                                        # notices a spider
                     (0.25, {"j2": -0.4, "j3": -1.2, "j6": -2.2, "j8": 3.5}),  # recoils
                     (0.15, {"j6": -1.6}), (0.15, {"j6": -2}), (0.15, {"j6": -1.6}), (0.15, {"j6": -2}),
                     (2, {"j1": -1.5, "j8": 0}), (2, {"j1": 0, "j2": 0, "j3": 0, "j6": 0})],
}
GESTURES.update(SCENES)

# Props the viewer draws for some scenes, tied to the start time of a keyframe (index into the scene).
PROPS: dict[str, dict] = {
    "kick_ball":    {"type": "kick", "at": 3},
    "put_on_hat":   {"type": "hat", "grab": 4, "toss": 7, "land": 8},
    "air_kiss":     {"type": "heart", "at": 3},
    "sniff_flower": {"type": "flower", "at": 2},
    "catch_ball":   {"type": "catch", "at": 3},
    "scared":       {"type": "spider", "at": 1},
}


@dataclass
class Step:
    t: float                          # seconds from the start of the gesture
    goals: dict[str, float]           # absolute norm targets
    acc: dict[str, int]
    speed: dict[str, int]
    wait_arrival: bool = False        # bound flow: wait until joints arrive before the next step
    key: int = -1                     # index of the keyframe this step starts (for props and timing)


def _settings(p: Personality, joints) -> tuple[dict[str, int], dict[str, int]]:
    acc = {j: int(max(5, min(ACC_CAP[j], BASE[j][0] * (min(p.acc, 1.0) if j == "j2" else p.acc)))) for j in joints}
    speed = {j: int(max(100, min(SPEED_CAP[j], BASE[j][1] * p.speed))) for j in joints}
    return acc, speed


def _clamp(j: str, neutral: dict[str, float], v: float) -> float:
    lo, hi = neutral[j] - MAX_DEV[j], neutral[j] + MAX_DEV[j]
    return max(0.0, min(1.0, max(lo, min(hi, v))))


def stance(p: Personality, neutral: dict[str, float]) -> dict[str, float]:
    """The personality's standing posture."""
    return {j: _clamp(j, neutral, neutral[j] + SIGN[j] * p.posture.get(j, 0.0)) for j in JOINTS}


def _min_jerk(x: float) -> float:
    """Minimum-jerk profile 0..1 (zero velocity and acceleration at both ends)."""
    x = max(0.0, min(1.0, x))
    return x * x * x * (10 - 15 * x + 6 * x * x)


def _smooth_plan(p: Personality, gesture: str, neutral: dict[str, float], rate_hz: float = 20.0) -> list[Step]:
    """Each keyframe becomes a minimum-jerk curve sampled at rate_hz; consecutive curves join with
    zero velocity, so the motion never jerks. The servo only has to track small, even steps."""
    base = stance(p, neutral)
    acc, speed = _settings(p, JOINTS)
    cur, t, steps = dict(base), 0.0, []
    keys = [(b, offs) for b, offs in GESTURES[gesture]] + [(1.5, {j: 0.0 for j in JOINTS})]
    for ki, (beats, offs) in enumerate(keys):
        first = len(steps)
        dur = beats * p.tempo
        target = dict(cur)
        for j, o in offs.items():
            target[j] = _clamp(j, neutral, base[j] + SIGN[j] * o * U * p.size)
        moved = [j for j in JOINTS if abs(target[j] - cur[j]) > 1e-4]
        n = max(1, int(round(dur * rate_hz)))
        for k in range(1, n + 1):
            f = _min_jerk(k / n)
            goals = {j: cur[j] + (target[j] - cur[j]) * f for j in moved}
            if goals or k == n:
                steps.append(Step(t + k / rate_hz, goals, acc, speed))
        if ki < len(keys) - 1 and len(steps) > first:
            steps[first].key = ki
        t += n / rate_hz
        cur = target
    steps.append(Step(t, {j: base[j] for j in JOINTS}, acc, speed, wait_arrival=True))
    return steps


def plan(p: Personality | str, gesture: str, neutral: dict[str, float] | None = None,
         seed: int | None = 0) -> list[Step]:
    """Turn one gesture into timed goal steps in this personality's style. Pure function."""
    p = PERSONALITIES[p] if isinstance(p, str) else p
    neutral = neutral or {j: 0.5 for j in JOINTS}
    if p.smooth:
        return _smooth_plan(p, gesture, neutral)
    rng = random.Random(seed)
    base = stance(p, neutral)
    cur = dict(base)
    t, steps = 0.0, []
    for ki, (beats, offs) in enumerate(GESTURES[gesture]):
        first = len(steps)
        dur = beats * p.tempo
        target = dict(cur)
        for j, o in offs.items():
            target[j] = _clamp(j, neutral, base[j] + SIGN[j] * o * U * p.size)
        moved = [j for j in JOINTS if abs(target[j] - cur[j]) > 1e-4]
        acc, speed = _settings(p, JOINTS)
        if moved and p.anticipation > 0 and max(abs(target[j] - cur[j]) for j in moved) > 0.03:
            pre = {j: _clamp(j, neutral, cur[j] - p.anticipation * (target[j] - cur[j])) for j in moved}
            steps.append(Step(t, pre, acc, speed))
            t += 0.25 * dur
            dur *= 0.75
        if moved and p.overshoot > 0:
            over = {j: _clamp(j, neutral, target[j] + p.overshoot * (target[j] - cur[j])) for j in moved}
            steps.append(Step(t, over, acc, speed))
            t += 0.45 * dur
            dur *= 0.55
        goals = {j: target[j] for j in (moved or [])}
        if p.tremor:
            for j in ("j6", "j7"):
                goals[j] = _clamp(j, neutral, target[j] + rng.uniform(-p.tremor, p.tremor))
        steps.append(Step(t, goals, acc, speed, wait_arrival=p.blend == 0.0 and bool(moved)))
        steps[first].key = ki
        t += dur * (1.0 - p.blend) if p.blend else dur
        cur = target
    steps.append(Step(t, {j: base[j] for j in JOINTS}, *_settings(p, JOINTS), wait_arrival=True))
    return steps


def idle_plan(p: Personality | str, seconds: float, neutral: dict[str, float] | None = None,
              seed: int | None = 0, rate_hz: float = 5.0) -> list[Step]:
    """Breathing (j3/j6 sine) plus occasional glances (j1, j7) for `seconds`."""
    p = PERSONALITIES[p] if isinstance(p, str) else p
    neutral = neutral or {j: 0.5 for j in JOINTS}
    if p.smooth:
        rate_hz = 20.0
    rng = random.Random(seed)
    base = stance(p, neutral)
    acc, speed = _settings(p, JOINTS)
    steps, glance = [], {"j1": base["j1"], "j7": base["j7"]}
    next_glance = rng.expovariate(1 / p.glance_s) if p.glance_s else math.inf
    n = int(seconds * rate_hz)
    for k in range(n + 1):
        t = k / rate_hz
        b = p.breath * math.sin(2 * math.pi * t / p.breath_s)
        goals = {"j3": _clamp("j3", neutral, base["j3"] + SIGN["j3"] * b),
                 "j6": _clamp("j6", neutral, base["j6"] - SIGN["j6"] * 0.6 * b)}
        if t >= next_glance:
            glance = {"j1": _clamp("j1", neutral, base["j1"] + SIGN["j1"] * rng.uniform(-1.0, 1.0) * U * p.size),
                      "j7": _clamp("j7", neutral, base["j7"] + SIGN["j7"] * rng.uniform(-0.5, 0.5) * U * p.size)}
            next_glance = t + rng.expovariate(1 / p.glance_s)
        goals.update(glance)
        if p.tremor:
            goals["j7"] = _clamp("j7", neutral, goals["j7"] + rng.uniform(-p.tremor, p.tremor))
        steps.append(Step(t, goals, acc, speed))
    return steps


# ----------------------------------------------------------------------------- on the real arm

async def _send(arm, step: Step) -> None:
    from elrobot import REG_ACC, REG_SPEED, norm_to_raw, send_commands, sync_write, REG_GOAL
    bus = arm._buses.get(arm.follower) or await arm.state()
    arm.check_faults(bus)
    ids = {int(j[1:]): j for j in step.goals}
    goals = {}
    for mid, j in ids.items():
        m = bus.motors[mid]
        goals[mid] = norm_to_raw(step.goals[j], m.range_min, m.range_max).to_bytes(2, "little")
    # speed, acceleration and goal in one message: one round trip to Station
    await send_commands(arm.client, [
        sync_write(arm.follower, REG_SPEED, {mid: step.speed[j].to_bytes(2, "little") for mid, j in ids.items()}),
        sync_write(arm.follower, REG_ACC, {mid: bytes([step.acc[j]]) for mid, j in ids.items()}),
        sync_write(arm.follower, REG_GOAL, goals),
    ])


async def _wait_arrival(arm, goals: dict[str, float], tol: float = 0.02, timeout: float = 2.0) -> None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        bus = await arm.state()
        if all(abs(bus.motors[int(j[1:])].norm - v) <= tol for j, v in goals.items()):
            return
        await asyncio.sleep(0.01)


async def play(arm, steps: list[Step]) -> None:
    loop = asyncio.get_running_loop()
    t0 = loop.time()
    for s in steps:
        delay = t0 + s.t - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        await _send(arm, s)
        if s.wait_arrival:
            before = loop.time()
            await _wait_arrival(arm, s.goals)
            t0 += loop.time() - before          # keep the rest of the timing relative to arrival


async def neutral_pose(arm) -> dict[str, float]:
    """The taught 'neutral' pose if there is one, else wherever the arm is now."""
    import json
    from elrobot import HERE
    path = HERE / "poses.json"
    poses = json.loads(path.read_text()) if path.exists() else {}
    return poses.get("neutral") or await arm.joints()


async def perform(arm, personality: str, gesture: str, neutral: dict[str, float] | None = None) -> None:
    neutral = neutral or await neutral_pose(arm)
    await play(arm, plan(personality, gesture, neutral, seed=None))


async def idle(arm, personality: str, seconds: float = 10.0, neutral: dict[str, float] | None = None) -> None:
    neutral = neutral or await neutral_pose(arm)
    await play(arm, idle_plan(personality, seconds, neutral, seed=None))
