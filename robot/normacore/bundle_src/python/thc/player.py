"""Play planned steps on any robot through two small functions you write.

    def send(goals, acc, speed):   # goals: {joint: 0..1}, acc/speed: STS3215 units per joint
        ...                        # convert with thc.units if your servos are not STS3215
    def read():                    # optional: current positions {joint: 0..1}; enables real arrival waits
        ...

    play(steps, send, read)                    # blocking
    await aplay(steps, send_async, read_async) # asyncio version (send/read may be sync or async)

Without read(), "bound" steps wait for an estimate of how long the servo needs (trapezoid profile).
"""
from __future__ import annotations

import asyncio
import inspect
import math
import time
from typing import Callable

from .planner import Step
from .units import TICK_RAD

ARRIVE_TOL = 0.02          # normalized
ARRIVE_TIMEOUT = 2.0       # s


def move_time(dist_norm: float, acc: int, speed: int, range_rad: float = 3.2) -> float:
    """Seconds an STS3215 needs for a move of dist_norm (trapezoid: accelerate, cruise, brake)."""
    d = abs(dist_norm) * range_rad / TICK_RAD                    # ticks
    a, v = max(1, acc) * 100.0, max(1, speed)                    # ticks/s^2, ticks/s
    if d <= v * v / a:
        return 2 * math.sqrt(d / a)
    return v / a + d / v


def _estimate(step: Step, last: dict[str, float]) -> float:
    return max((move_time(v - last.get(j, v), step.acc[j], step.speed[j]) for j, v in step.goals.items()), default=0.0)


def play(steps: list[Step], send: Callable, read: Callable | None = None,
         sleep: Callable = time.sleep, clock: Callable = time.monotonic) -> None:
    t0, last = clock(), {}
    for s in steps:
        delay = t0 + s.t - clock()
        if delay > 0:
            sleep(delay)
        send(s.goals, {j: s.acc[j] for j in s.goals}, {j: s.speed[j] for j in s.goals})
        if s.wait_arrival:
            start = clock()
            if read:
                while clock() - start < ARRIVE_TIMEOUT:
                    now = read()
                    if all(abs(now.get(j, v) - v) <= ARRIVE_TOL for j, v in s.goals.items()):
                        break
                    sleep(0.01)
            else:
                sleep(_estimate(s, last))
            t0 += clock() - start                       # later steps keep their spacing after the wait
        last.update(s.goals)


async def _call(f, *a):
    r = f(*a)
    return await r if inspect.isawaitable(r) else r


async def aplay(steps: list[Step], send: Callable, read: Callable | None = None) -> None:
    loop = asyncio.get_running_loop()
    t0, last = loop.time(), {}
    for s in steps:
        delay = t0 + s.t - loop.time()
        if delay > 0:
            await asyncio.sleep(delay)
        await _call(send, s.goals, {j: s.acc[j] for j in s.goals}, {j: s.speed[j] for j in s.goals})
        if s.wait_arrival:
            start = loop.time()
            if read:
                while loop.time() - start < ARRIVE_TIMEOUT:
                    now = await _call(read)
                    if all(abs(now.get(j, v) - v) <= ARRIVE_TOL for j, v in s.goals.items()):
                        break
                    await asyncio.sleep(0.01)
            else:
                await asyncio.sleep(_estimate(s, last))
            t0 += loop.time() - start
        last.update(s.goals)
