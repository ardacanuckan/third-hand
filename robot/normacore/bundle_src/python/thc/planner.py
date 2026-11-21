"""Plan a gesture or scene in a character's style: timed joint goals with per-joint acceleration and speed.

Pure Python, standard library only. Same rules as Third Hand's character.py (verified step for step).

    from thc import Library
    lib = Library.load()                                 # reads characters.json next to the package
    steps = lib.plan("trickster", "kick_ball")           # or your own keyframes: [[beats, {"j6": 1.0}], ...]
    for s in steps: print(s.t, s.goals, s.acc, s.speed, s.wait_arrival)
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_JSON = Path(__file__).resolve().parent.parent.parent / "characters.json"
Keyframes = list  # [[beats, {joint: offset_units}], ...]


@dataclass
class Step:
    t: float                          # seconds from the start (shifted later if a bound step waits)
    goals: dict[str, float]           # target positions, normalized 0..1 per joint
    acc: dict[str, int]               # STS3215 acceleration units (100 ticks/s^2) per joint
    speed: dict[str, int]             # STS3215 speed, ticks/s, per joint
    wait_arrival: bool = False        # wait until these joints arrive before the next step
    key: int = -1                     # index of the keyframe this step starts (props, sync)


@dataclass
class Character:
    name: str
    archetype: str
    laban: str
    acc_mult: float
    speed_mult: float
    size: float
    tempo: float
    blend: float
    anticipation: float
    overshoot: float
    tremor: float
    posture: dict = field(default_factory=dict)
    breath: float = 0.01
    breath_s: float = 4.0
    glance_s: float = 0.0
    smooth: bool = False


class Library:
    """Everything in characters.json, plus the planner."""

    def __init__(self, data: dict):
        self.data = data
        self.joints: list[str] = data["joints"]["names"]
        lim = data["limits"]
        self.max_dev: dict[str, float] = lim["max_dev_from_neutral"]
        self.acc_cap: dict[str, int] = lim["acc_cap"]
        self.speed_cap: dict[str, int] = lim["speed_cap"]
        self.base = {j: (v["acc"], v["speed"]) for j, v in lim["base_profile"].items()}
        self.sign: dict[str, float] = dict(lim["sign"])
        self.unit: float = data["units"]["offset_unit"]
        self.characters = {n: Character(name=n, **c) for n, c in data["characters"].items()}
        self.moves: dict[str, Keyframes] = {**data["gestures"], **data["scenes"]}
        self.scenes = list(data["scenes"])
        self.props: dict = data.get("props", {})

    @classmethod
    def load(cls, path: str | Path = DEFAULT_JSON) -> "Library":
        return cls(json.loads(Path(path).read_text()))

    # ------------------------------------------------------------------ helpers

    def settings(self, c: Character) -> tuple[dict[str, int], dict[str, int]]:
        """Per-joint acceleration and speed for this character (shoulder never sudden; caps applied)."""
        acc = {j: int(max(5, min(self.acc_cap[j], self.base[j][0] * (min(c.acc_mult, 1.0) if j == "j2" else c.acc_mult))))
               for j in self.joints}
        speed = {j: int(max(100, min(self.speed_cap[j], self.base[j][1] * c.speed_mult))) for j in self.joints}
        return acc, speed

    def clamp(self, j: str, neutral: dict[str, float], v: float) -> float:
        lo, hi = neutral[j] - self.max_dev[j], neutral[j] + self.max_dev[j]
        return max(0.0, min(1.0, max(lo, min(hi, v))))

    def stance(self, c: Character, neutral: dict[str, float]) -> dict[str, float]:
        return {j: self.clamp(j, neutral, neutral[j] + self.sign[j] * c.posture.get(j, 0.0)) for j in self.joints}

    def _char(self, c: Character | str) -> Character:
        return self.characters[c] if isinstance(c, str) else c

    def _keys(self, move: str | Keyframes) -> Keyframes:
        return self.moves[move] if isinstance(move, str) else move

    # ------------------------------------------------------------------ planning

    def plan(self, character: Character | str, move: str | Keyframes, neutral: dict[str, float] | None = None,
             seed: int | None = 0) -> list[Step]:
        """Timed steps for one gesture/scene (by name) or your own keyframes, in this character's style."""
        c = self._char(character)
        neutral = neutral or {j: 0.5 for j in self.joints}
        if c.smooth:
            return self._smooth(c, self._keys(move), neutral)
        rng = random.Random(seed)
        base = self.stance(c, neutral)
        cur, t, steps = dict(base), 0.0, []
        acc, speed = self.settings(c)
        for ki, (beats, offs) in enumerate(self._keys(move)):
            first = len(steps)
            dur = beats * c.tempo
            target = dict(cur)
            for j, o in offs.items():
                target[j] = self.clamp(j, neutral, base[j] + self.sign[j] * o * self.unit * c.size)
            moved = [j for j in self.joints if abs(target[j] - cur[j]) > 1e-4]
            if moved and c.anticipation > 0 and max(abs(target[j] - cur[j]) for j in moved) > 0.03:
                pre = {j: self.clamp(j, neutral, cur[j] - c.anticipation * (target[j] - cur[j])) for j in moved}
                steps.append(Step(t, pre, acc, speed)); t += 0.25 * dur; dur *= 0.75
            if moved and c.overshoot > 0:
                over = {j: self.clamp(j, neutral, target[j] + c.overshoot * (target[j] - cur[j])) for j in moved}
                steps.append(Step(t, over, acc, speed)); t += 0.45 * dur; dur *= 0.55
            goals = {j: target[j] for j in moved}
            if c.tremor:
                for j in ("j6", "j7"):
                    goals[j] = self.clamp(j, neutral, target[j] + rng.uniform(-c.tremor, c.tremor))
            steps.append(Step(t, goals, acc, speed, wait_arrival=c.blend == 0.0 and bool(moved)))
            steps[first].key = ki
            t += dur * (1.0 - c.blend) if c.blend else dur
            cur = target
        steps.append(Step(t, dict(base), acc, speed, wait_arrival=True))
        return steps

    def _smooth(self, c: Character, keyframes: Keyframes, neutral: dict[str, float], rate_hz: float = 20.0) -> list[Step]:
        """Minimum-jerk curves sampled at rate_hz instead of jumps between poses."""
        base = self.stance(c, neutral)
        acc, speed = self.settings(c)
        cur, t, steps = dict(base), 0.0, []
        keys = list(keyframes) + [[1.5, {j: 0.0 for j in self.joints}]]
        for ki, (beats, offs) in enumerate(keys):
            first = len(steps)
            dur = beats * c.tempo
            target = dict(cur)
            for j, o in offs.items():
                target[j] = self.clamp(j, neutral, base[j] + self.sign[j] * o * self.unit * c.size)
            moved = [j for j in self.joints if abs(target[j] - cur[j]) > 1e-4]
            n = max(1, int(round(dur * rate_hz)))
            for k in range(1, n + 1):
                x = k / n
                f = x * x * x * (10 - 15 * x + 6 * x * x)
                goals = {j: cur[j] + (target[j] - cur[j]) * f for j in moved}
                if goals or k == n:
                    steps.append(Step(t + k / rate_hz, goals, acc, speed))
            if ki < len(keys) - 1 and len(steps) > first:
                steps[first].key = ki
            t += n / rate_hz
            cur = target
        steps.append(Step(t, dict(base), acc, speed, wait_arrival=True))
        return steps

    def idle(self, character: Character | str, seconds: float, neutral: dict[str, float] | None = None,
             seed: int | None = 0, rate_hz: float = 5.0) -> list[Step]:
        """Breathing plus occasional glances, for standing around between moves."""
        c = self._char(character)
        neutral = neutral or {j: 0.5 for j in self.joints}
        if c.smooth:
            rate_hz = 20.0
        rng = random.Random(seed)
        base = self.stance(c, neutral)
        acc, speed = self.settings(c)
        steps, glance = [], {"j1": base["j1"], "j7": base["j7"]}
        next_glance = rng.expovariate(1 / c.glance_s) if c.glance_s else math.inf
        for k in range(int(seconds * rate_hz) + 1):
            t = k / rate_hz
            b = c.breath * math.sin(2 * math.pi * t / c.breath_s)
            goals = {"j3": self.clamp("j3", neutral, base["j3"] + self.sign["j3"] * b),
                     "j6": self.clamp("j6", neutral, base["j6"] - self.sign["j6"] * 0.6 * b)}
            if t >= next_glance:
                glance = {"j1": self.clamp("j1", neutral, base["j1"] + self.sign["j1"] * rng.uniform(-1, 1) * self.unit * c.size),
                          "j7": self.clamp("j7", neutral, base["j7"] + self.sign["j7"] * rng.uniform(-0.5, 0.5) * self.unit * c.size)}
                next_glance = t + rng.expovariate(1 / c.glance_s)
            goals.update(glance)
            if c.tremor:
                goals["j7"] = self.clamp("j7", neutral, goals["j7"] + rng.uniform(-c.tremor, c.tremor))
            steps.append(Step(t, goals, acc, speed))
        return steps
