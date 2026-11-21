"""Translate arm movement into words an LLM can read: what moved, how far, how fast, and when the jaws gripped.

    from motion_to_text import Frame, describe
    text = describe(frames).text            # frames: list of Frame(t, pos {j: 0..1}, current {j: mA}, ranges {j: (min, max)})

Uses: the LLM gets a short account of what the arm actually did after a tool call (no picture-by-picture);
episodes get step-by-step captions for training data; characters can be checked against their intent.

    python3 motion_to_text.py episode.parquet [...]      # needs pyarrow for parquet; the core is stdlib only

Directions: `DIRECTION` names what + means for each joint. The pitch joints and the jaws follow the
ElRobot URDF; j1/j5/j7 left/right depends on calibration: check once (jog j1 by +0.05 and look) and flip it.
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field

JOINTS = ("j1", "j2", "j3", "j4", "j5", "j6", "j7", "j8")
TICKS_PER_DEG = 4096 / 360
# What a positive change in position_norm looks like, as (verb for +, verb for -).
DIRECTION = {
    "j1": ("turns left", "turns right"),            # check on your arm
    "j2": ("leans forward", "leans back"),
    "j3": ("lowers the arm", "raises the arm"),
    "j4": ("tips the forearm down", "tips the forearm up"),
    "j5": ("twists left", "twists right"),          # check on your arm
    "j6": ("tilts the wrist down", "tilts the wrist up"),
    "j7": ("rolls the gripper left", "rolls the gripper right"),   # check on your arm
    "j8": ("opens the jaws", "closes the jaws"),
}
MOVE_SPEED = 0.04          # norm/s: above this a joint counts as moving
MIN_SEGMENT_S = 0.3        # shorter moves/pauses merge into neighbours
MIN_DELTA = 0.025          # norm: smaller changes are not mentioned
GRIP_MA = 150              # jaw current spike while closing = squeezing something
GRIP_GAP = 0.06            # or: the jaws were commanded this much tighter than they got (blocked)
GRIP_CLOSE = 0.10          # norm: a grasp closes the jaws at least this much (small twitches are not grasps)
JAWS_CLOSED = 0.08         # norm: jaws that settle below this closed on nothing
RELEASE_OPEN = 0.15        # norm: opening this far past the grip position = letting go; less is loosening
# Tuned on the 21 Nov glue-stick episodes against the wrist camera: a 0.11 loosening kept the stick,
# a 0.06 close with a 0.04 goal gap held nothing.


@dataclass
class Frame:
    t: float                                        # seconds
    pos: dict[str, float]                           # position_norm 0..1
    current: dict[str, float] = field(default_factory=dict)       # mA, optional
    goal: dict[str, float] = field(default_factory=dict)          # commanded position_norm, optional
    ranges: dict[str, tuple[int, int]] = field(default_factory=dict)  # calibrated ticks, optional (for degrees)


@dataclass
class Segment:
    t0: float
    t1: float
    moving: bool
    changes: dict[str, float]                       # joint -> norm delta over the segment
    degrees: dict[str, float]                       # joint -> degrees (if ranges known)
    peak_deg_s: float
    events: list[str]
    phrase: str = ""


@dataclass
class Description:
    segments: list[Segment]
    events: list[tuple[float, str]]
    text: str                                       # numbered account, one line per segment
    summary: str                                    # one paragraph for an LLM tool result

    def as_json(self) -> str:
        return json.dumps({"summary": self.summary, "events": self.events,
                           "segments": [{"t0": round(s.t0, 2), "t1": round(s.t1, 2), "moving": s.moving,
                                         "phrase": s.phrase, "events": s.events,
                                         "degrees": {j: round(v, 1) for j, v in s.degrees.items()}}
                                        for s in self.segments]}, indent=1)


def _deg(frame: Frame, j: str, dnorm: float) -> float | None:
    r = frame.ranges.get(j)
    return dnorm * (r[1] - r[0]) / TICKS_PER_DEG if r else None


def _size(deg: float | None, dnorm: float) -> str:
    if deg is not None:
        return f"{abs(deg):.0f}°"
    return "a little" if abs(dnorm) < 0.06 else "a lot" if abs(dnorm) > 0.2 else "some way"


def _speed_word(peak: float, dur: float) -> str:
    if peak > 90: return "quickly"
    if peak < 20 and dur > 1.5: return "slowly"
    return ""


def _smooth(vals: list[float], k: int = 2) -> list[float]:
    return [sum(vals[max(0, i - k):i + k + 1]) / len(vals[max(0, i - k):i + k + 1]) for i in range(len(vals))]


def _grip_events(frames: list[Frame], T: list[float], jaw: list[float] | None) -> list[tuple[float, str]]:
    """Grip = the jaws close, stop short of shut, and squeezed on the way (current spike or blocked goal).
    Held until the jaws open noticeably past where they stopped. Holding current is near zero, so
    current alone cannot tell holding from empty."""
    if not jaw:
        return []
    out, held_at, i, n = [], None, 1, len(frames)
    while i < n:
        dt = max(1e-6, T[i] - T[i - 1])
        if (jaw[i] - jaw[i - 1]) / dt < -MOVE_SPEED:                 # a closing move starts
            a = i - 1
            while i < n and (jaw[i] - jaw[i - 1]) / max(1e-6, T[i] - T[i - 1]) < -MOVE_SPEED / 2:
                i += 1
            b = min(i, n - 1)                                        # settled
            squeeze = max(frames[k].current.get("j8", 0) for k in range(a, min(n, b + 3)))
            # blocked = still commanded tighter AFTER the jaws stopped (while closing, the goal always leads)
            blocked = min((frames[k].goal.get("j8", jaw[k]) - frames[k].pos.get("j8", jaw[k])) for k in range(b, min(n, b + 4)))
            stop = frames[b].pos.get("j8", jaw[b])
            closed_by = frames[a].pos.get("j8", jaw[a]) - stop
            evidence = squeeze >= GRIP_MA or blocked <= -GRIP_GAP
            if closed_by >= GRIP_CLOSE and evidence:
                if held_at is None:
                    why = f"{squeeze:.0f} mA" if squeeze >= GRIP_MA else "jaws blocked"
                    small = " (a thin part)" if stop <= JAWS_CLOSED + 0.04 else ""
                    out.append((T[b], f"grips something{small} (jaws stopped {stop:.0%} open, {why})"))
                held_at = stop
            elif closed_by >= GRIP_CLOSE and held_at is None and stop < 0.5:
                out.append((T[b], "EMPTY_CLOSE"))            # ends well closed with no squeeze: nothing there
            elif stop <= JAWS_CLOSED and held_at is not None and not evidence:
                out.append((T[b], "closes the jaws fully: nothing in them any more")); held_at = None
            continue
        if held_at is not None and jaw[i] > held_at + RELEASE_OPEN:
            out.append((T[i], "lets go")); held_at = None
        i += 1
    # an empty close followed by a grasp is a missed grasp; otherwise the jaws are just being closed
    named = []
    for k, (t, e) in enumerate(out):
        if e == "EMPTY_CLOSE":
            later_grip = any(x.startswith("grips") for _, x in out[k + 1:])
            e = "closes the jaws on nothing: a missed grasp" if later_grip else "closes the jaws (nothing between them)"
        named.append((t, e))
    return named


def _pull_before(frames: list[Frame], t_release: float) -> dict | None:
    """Did someone pull on the held object just before the jaws opened? Runs handover.PullDetector over
    the 2.5 s before the release (baseline from its first 0.5 s, while the arm holds still)."""
    from handover import PullDetector
    win = [f for f in frames if t_release - 2.5 <= f.t <= t_release - 0.05]
    if len(win) < 8:
        return None
    # only meaningful while the arm is told to stay put: commanded positions steady over the window
    if win[0].goal:
        for j in ("j1", "j2", "j3", "j4", "j6"):
            g = [f.goal.get(j) for f in win if j in f.goal]
            if g and max(g) - min(g) > 0.012:
                return None
    det = PullDetector({"baseline_s": 0.5, "hold_s": 0.15})
    for f in win:
        ev = det.update(f.t, f.pos, f.current, f.ranges)
        if ev:
            return ev
    return None


def _fault_events(frames: list[Frame], T: list[float]) -> list[tuple[float, str]]:
    """An arm joint that stays far from its goal for over 0.8 s WITHOUT closing the gap has stopped
    following: an overload trip or torque off. A follower that merely trails the leader (~0.3 s on the
    real arm) keeps catching up, so it is not reported."""
    out = []
    if not frames or not frames[0].goal:
        return out
    for j in JOINTS[:7]:
        start = None
        for f in frames:
            off = abs(f.goal.get(j, f.pos.get(j, 0)) - f.pos.get(j, 0))
            if off > 0.08:
                if start is None:
                    start, p0, off0 = f.t, f.pos.get(j, 0), off
                elif f.t - start >= 0.8:
                    toward = abs(f.goal.get(j, 0) - p0) - abs(f.goal.get(j, 0) - f.pos.get(j, 0))
                    if toward < 0.3 * off0 and off >= 0.7 * off0:
                        out.append((start, f"{j} stops following its commands (overload or torque off?)")); break
                    start = None
            else:
                start = None
    return out


def describe(frames: list[Frame]) -> Description:
    if len(frames) < 3:
        return Description([], [], "Not enough data.", "Not enough data.")
    T = [f.t for f in frames]
    P = {j: _smooth([f.pos.get(j, math.nan) for f in frames]) for j in JOINTS if j in frames[0].pos}
    joints = list(P)
    # moving or still, frame by frame (arm joints; jaws count too)
    moving = []
    for i in range(len(frames)):
        a, b = max(0, i - 1), min(len(frames) - 1, i + 1)
        dt = max(1e-6, T[b] - T[a])
        moving.append(any(abs(P[j][b] - P[j][a]) / dt > MOVE_SPEED for j in joints))
    # runs, then merge short ones into the previous run
    runs = []
    for i, m in enumerate(moving):
        if runs and runs[-1][2] == m:
            runs[-1][1] = i
        else:
            runs.append([i, i, m])
    merged = []
    for r in runs:
        if merged and (T[r[1]] - T[r[0]] < MIN_SEGMENT_S or (T[merged[-1][1]] - T[merged[-1][0]] < MIN_SEGMENT_S)):
            merged[-1][1] = r[1]; merged[-1][2] = merged[-1][2] or r[2]
        else:
            merged.append(r)
    events = sorted(_grip_events(frames, T, P.get("j8")) + _fault_events(frames, T))
    for k, (t, e) in enumerate(events):
        if e == "lets go":
            pull = _pull_before(frames, t)
            if pull:
                events[k] = (t, f"lets go after a pull ({pull['joint']}: +{pull['current_ma']} mA, {pull['deflection_deg']} deg give, "
                                f"{t - pull['pull_started']:.1f} s after the pull began)")
    segs = []
    for a, b, m in merged:
        ch = {j: P[j][b] - P[j][a] for j in joints}
        deg = {j: d for j in joints if (d := _deg(frames[a], j, ch[j])) is not None}
        peak = 0.0
        for i in range(a + 1, b + 1):
            dt = max(1e-6, T[i] - T[i - 1])
            for j in joints:
                d = _deg(frames[i], j, P[j][i] - P[j][i - 1])
                if d is not None and j != "j8":
                    peak = max(peak, abs(d) / dt)
        ev = [e for t, e in events if T[a] <= t <= T[b] + 1e-9]
        segs.append(Segment(T[a], T[b], m, ch, deg, peak, ev))
    # holding intervals -> phase names: carrying while holding, reaching before a (next) grip, returning after the last
    holds, start = [], None
    for t, e in events:
        if e.startswith("grips"): start = t
        elif start is not None and (e.startswith("lets go") or e.startswith("closes the jaws fully")): holds.append((start, t)); start = None
    if start is not None: holds.append((start, math.inf))
    grip_times = [h[0] for h in holds]

    def phase_of(t_mid: float) -> str:
        if not holds: return ""
        if any(a <= t_mid < b for a, b in holds): return "carrying: "
        if any(g > t_mid for g in grip_times): return "reaching: " if t_mid < grip_times[0] else "reaching again: "
        return "returning: "
    lines, summary_bits = [], []
    for k, s in enumerate(segs):
        dur = s.t1 - s.t0
        if s.moving:
            parts = []
            for j in sorted(s.changes, key=lambda j: -abs(s.changes[j])):
                d = s.changes[j]
                if abs(d) < MIN_DELTA:
                    continue
                if j == "j8" and any(e.startswith("grips") for e in s.events):
                    continue                                   # the grip event says it better
                verb = DIRECTION[j][0 if d > 0 else 1]
                parts.append(f"{verb} {_size(s.degrees.get(j), d)}")
            phase = phase_of((s.t0 + s.t1) / 2)
            sp = _speed_word(s.peak_deg_s, dur)
            body = ", ".join(parts[:4]) or "small adjustments"
            s.phrase = f"{phase}{body}{', ' + sp if sp else ''}"
        else:
            s.phrase = "holds still"
        if s.events:
            s.phrase += "; " + "; ".join(s.events)
        lines.append(f"{k + 1:>2}. {s.t0:5.1f}-{s.t1:5.1f} s  {s.phrase}")
        if s.moving or s.events:
            summary_bits.append(s.phrase)
    total = T[-1] - T[0]
    still = sum(s.t1 - s.t0 for s in segs if not s.moving)
    nm = sum(s.moving for s in segs)
    head = f"Over {total:.0f} s the arm moved in {nm} stretch{'es' if nm != 1 else ''} and held still for {still:.0f} s."
    if holds:
        parts = [f"{a:.1f} s" + (f" (let go at {b:.1f} s)" if b != math.inf else " (still holding at the end)") for a, b in holds]
        head += f" It gripped {len(holds)} time{'s' if len(holds) > 1 else ''}: " + ", ".join(parts) + "."
        if len(holds) > 1 and holds[0][1] - holds[0][0] < 2.0:
            head += " The first grip was let go within 2 s: probably a failed grasp, then a retry."
    else:
        head += " The jaws never closed on anything."
    misses = sum(e.endswith("a missed grasp") for _, e in events)
    if misses:
        head += f" {misses} grasp{'s' if misses > 1 else ''} closed on nothing."
    faults = [e for _, e in events if "stops following" in e]
    if faults:
        head += " Fault: " + "; ".join(faults) + "."
    gaps = sum(1 for a, b in zip(T, T[1:]) if b - a > 0.25)
    if gaps:
        head += f" Note: {gaps} gap{'s' if gaps > 1 else ''} in the recording (frames missing)."
    summary = head + " Sequence: " + "; then ".join(summary_bits[:12]) + ("…" if len(summary_bits) > 12 else ".")
    return Description(segs, events, "\n".join(lines), summary)


# ----------------------------------------------------------------------------- sources

def frames_from_parquet(path: str) -> list[Frame]:
    """A NormaCore Station episode (dataset-generator parquet)."""
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["timestamp_ns_since_episode_start", "joints"]).to_pydict()
    out = []
    for ts, js in zip(t["timestamp_ns_since_episode_start"], t["joints"]):
        out.append(Frame(ts / 1e9, {j: x["position_norm"] for j, x in zip(JOINTS, js)},
                         {j: x["current_ma"] for j, x in zip(JOINTS, js)},
                         {j: x["goal_norm"] for j, x in zip(JOINTS, js)},
                         {j: (x["range_min"], x["range_max"]) for j, x in zip(JOINTS, js)}))
    return out


def frame_from_bus(bus, t: float) -> Frame:
    """One live reading from elrobot.Bus (arm.state()). Collect these while a tool runs, then describe()."""
    pos, cur, rng = {}, {}, {}
    for mid, m in bus.motors.items():
        j = f"j{mid}"
        if j in JOINTS and m.calibrated:
            pos[j], cur[j], rng[j] = m.norm, float(m.current), (m.range_min, m.range_max)
    return Frame(t, pos, cur, {}, rng)


async def record(arm, motion, poll_s: float = 0.05) -> tuple[object, Description]:
    """Run an awaitable that moves the arm (e.g. arm.go_pose("home")) while sampling the motor bus;
    return (its result, a Description of what the arm actually did). For LLM tool results:

        result, d = await record(arm, arm.go_pose("handover"))
        return f"{result}. What the arm did: {d.summary}"
    """
    import asyncio
    import time as _time
    frames, t0, done = [], _time.monotonic(), asyncio.Event()

    async def sample():
        seq = -1
        while not done.is_set():
            if arm._seq != seq and arm.follower in arm._buses:
                seq = arm._seq
                frames.append(frame_from_bus(arm._buses[arm.follower], _time.monotonic() - t0))
            await asyncio.sleep(poll_s)

    task = asyncio.create_task(sample())
    try:
        result = await motion
    finally:
        await asyncio.sleep(2 * poll_s); done.set(); await task
    return result, describe(frames)


if __name__ == "__main__":
    for p in sys.argv[1:]:
        d = describe(frames_from_parquet(p))
        print(f"== {p.split('/')[-1]}\n{d.summary}\n\n{d.text}\n")
