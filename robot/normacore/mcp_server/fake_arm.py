"""A pretend ElRobot for the MCP server: same calls the tools use, joints that move at servo-like
speeds, a jaw that stalls on a pretend object (current spike), no cameras. For testing without hardware."""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

STAND = {"j1": 0.5, "j2": 0.53, "j3": 0.1, "j4": 0.76, "j5": 0.45, "j6": 0.73, "j7": 0.54, "j8": 0.6}
POSES = {"home": STAND, "park": {**STAND, "j1": 0.3, "j2": 0.5}, "handover": {**STAND, "j1": 0.62, "j2": 0.6, "j6": 0.8}}


@dataclass
class Motor:
    id: int
    norm: float
    current: int = 0
    range_min: int = 1024
    range_max: int = 3072
    overloaded: bool = False
    calibrated: bool = True

    @property
    def raw(self):
        return int(self.range_min + self.norm * (self.range_max - self.range_min))


class Bus:
    def __init__(self):
        self.motors = {int(j[1:]): Motor(int(j[1:]), v) for j, v in STAND.items()}


class FakeArm:
    follower = "FAKE-FOLLOWER"

    def __init__(self):
        self._buses = {self.follower: Bus()}
        self._seq = 0
        self.goal = dict(STAND)
        self.speed = {j: 0.6 for j in STAND}          # norm/s
        self.block = None                               # jaw stops here (an object between the jaws)
        self._task = None
        self.pull_at = None                             # loop time when a pretend person starts pulling

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def _run(self):
        dt = 0.02
        while True:
            bus = self._buses[self.follower]
            for mid, m in bus.motors.items():
                j = f"j{mid}"
                g = self.goal[j]
                if j == "j8" and self.block is not None and g < self.block:
                    g_eff = self.block
                else:
                    g_eff = g
                step = max(-self.speed[j] * dt, min(self.speed[j] * dt, g_eff - m.norm))
                m.norm += step
                stalled = j == "j8" and self.block is not None and g < self.block - 0.02 and abs(m.norm - self.block) < 0.01
                m.current = 450 if stalled else (8 if abs(step) > 1e-4 else 1)
            # a pretend person pulling on the held object: the shoulder and wrist push back and give a little
            now = asyncio.get_running_loop().time()
            if self.pull_at is not None and now >= self.pull_at and self.goal["j8"] < 0.5:
                ramp = min(1.0, (now - self.pull_at) / 0.3)
                for mid, rise, give in ((2, 420, 0.006), (6, 300, 0.004)):
                    bus.motors[mid].current = int(1 + rise * ramp)
                    bus.motors[mid].norm = self.goal[f"j{mid}"] + give * ramp
            self._seq += 1
            await asyncio.sleep(dt)

    async def state(self, timeout=2.0):
        return self._buses[self.follower]

    async def joints(self):
        return {f"j{m}": round(x.norm, 4) for m, x in self._buses[self.follower].motors.items()}

    async def _wait(self, joints, tol=0.01, timeout=6.0):
        t0 = asyncio.get_running_loop().time()
        while asyncio.get_running_loop().time() - t0 < timeout:
            bus = self._buses[self.follower]
            if all(abs(bus.motors[int(j[1:])].norm - (self.block if j == "j8" and self.block and self.goal[j] < self.block else self.goal[j])) < tol for j in joints):
                return
            await asyncio.sleep(0.02)

    async def move(self, targets, **kw):
        self.goal.update({j: max(0.0, min(1.0, v)) for j, v in targets.items()})
        await self._wait(list(targets))
        return await self.joints()

    async def gripper(self, norm, **kw):
        if norm >= 0.5:
            self.pull_at = None; self.block = None
        return await self.move({"j8": norm})

    async def hold(self):
        self.goal.update(await self.joints())

    async def torque(self, on, joints=None):
        return None

    async def frames(self, timeout=3.0):
        return []

    async def go_pose(self, name, **kw):
        if name not in POSES:
            raise KeyError(f"no pose {name!r}; fake poses: {', '.join(POSES)}")
        return await self.move(POSES[name])

    async def fake_pull_after(self, seconds: float):
        """For hand_over in fake mode: hold a pretend glue stick, then someone grabs and pulls after `seconds`."""
        if self.goal["j8"] >= 0.5:
            self.block = 0.36
            await self.move({"j8": 0.26})                            # squeeze: stalls on the stick
            await asyncio.sleep(0.3)
            self.goal["j8"] = 0.36                                   # relax, keep holding
        self.pull_at = asyncio.get_running_loop().time() + seconds

    async def play_steps(self, steps):
        """Character steps (character.plan) on the fake servos."""
        loop = asyncio.get_running_loop(); t0 = loop.time()
        for s in steps:
            await asyncio.sleep(max(0.0, t0 + s.t - loop.time()))
            for j in s.goals:
                self.speed[j] = min(2.0, max(0.2, s.speed[j] / 600 * 0.6))
            self.goal.update(s.goals)
            if s.wait_arrival:
                await self._wait(list(s.goals))
        for j in self.speed: self.speed[j] = 0.6

    async def fake_pick(self, width_mm):
        """Scripted stand-in for the trained policy: reach, close on the object, carry, hand over."""
        await self.move({"j8": 0.6})
        await self.move({"j1": 0.42, "j2": 0.62, "j6": 0.82})
        await self.move({"j3": 0.18})
        self.block = max(0.05, min(0.55, width_mm / 50))          # jaws stop at the object's width
        await self.move({"j8": self.block - 0.1})
        await asyncio.sleep(0.4)
        self.goal["j8"] = self.block                               # relax the squeeze, keep holding
        await self.move({"j3": 0.1, "j2": 0.55})
        await self.move({"j1": 0.62, "j6": 0.8})
        await asyncio.sleep(0.3)
        await self.move({"j8": 0.6}); self.block = None            # hand over
        await self.go_pose("home")
        return "fake policy finished (scripted stand-in)"

    def close_connection(self):
        if self._task: self._task.cancel()
