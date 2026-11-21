"""Where do the milliseconds go? Splits arm latency into its stages. Keep a hand on the power switch.

    python3 robot/normacore/examples/08_latency.py            # read-only: state rate, parse time, camera rate
    python3 robot/normacore/examples/08_latency.py j7 40      # also: command -> first visible motion (j7, 40 ticks)

Stages:
  1. state frame interval   how often Station publishes st3215 state (a read waits up to one interval)
  2. parse time             parse_state() per frame in Python
  3. command -> motion      sync_write goal sent -> position in the state stream moves >= 5 ticks
                            (= send + bus write + servo start-up/acceleration + one state interval)
  4. camera frame interval  inference/normvla rate (update-interval in station.yaml)
"""
import asyncio
import statistics
import sys
import time

from _common import ElRobot
from elrobot import NORMVLA_QUEUE, REG_ACC, REG_SPEED, parse_state, send_commands, sync_write


def summary(name: str, ms: list[float]) -> None:
    if not ms:
        print(f"{name:26s} no samples"); return
    ms = sorted(ms)
    p95 = ms[min(len(ms) - 1, int(len(ms) * 0.95))]
    print(f"{name:26s} n={len(ms):3d}  median {statistics.median(ms):6.1f} ms  p95 {p95:6.1f} ms  max {ms[-1]:6.1f} ms")


async def state_rate(arm: ElRobot, seconds: float = 3.0) -> list[float]:
    times, seq, end = [], arm._seq, time.monotonic() + seconds
    while time.monotonic() < end:
        if arm._seq != seq:
            seq = arm._seq; times.append(time.monotonic())
        await asyncio.sleep(0.0005)
    return [(b - a) * 1000 for a, b in zip(times, times[1:])]


async def camera_rate(arm: ElRobot, seconds: float = 3.0) -> list[float]:
    q: asyncio.Queue = asyncio.Queue()
    arm.client.follow(NORMVLA_QUEUE, q)
    times, end = [], time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            await asyncio.wait_for(q.get(), timeout=max(0.01, end - time.monotonic()))
            times.append(time.monotonic())
        except asyncio.TimeoutError:
            break
    return [(b - a) * 1000 for a, b in zip(times, times[1:])]


async def command_to_motion(arm: ElRobot, joint: str, ticks: int, trials: int = 6) -> list[float]:
    mid = int(joint[1:])
    out = []
    await arm.torque(True, (joint,))
    await send_commands(arm.client, [
        sync_write(arm.follower, REG_SPEED, {mid: (1500).to_bytes(2, "little")}),
        sync_write(arm.follower, REG_ACC, {mid: bytes([100])}),
    ])
    for k in range(trials):
        bus = await arm.state()
        m = bus.motors[mid]
        start_raw = m.raw
        goal = (start_raw + ticks * (1 if k % 2 == 0 else -1))
        goal_norm = (goal - m.range_min) / (m.range_max - m.range_min)
        t0 = time.monotonic()
        await arm._goals(bus, {mid: goal_norm})
        seq = arm._seq
        while time.monotonic() - t0 < 1.0:
            if arm._seq != seq:
                seq = arm._seq
                if abs(arm._buses[arm.follower].motors[mid].raw - start_raw) >= 5:
                    out.append((arm._buses[arm.follower].received - t0) * 1000); break
            await asyncio.sleep(0.0005)
        await asyncio.sleep(0.4)          # let it settle before the next trial
    return out


async def main():
    async with await ElRobot.connect() as arm:
        summary("1 state frame interval", await state_rate(arm))
        # 2: re-parse the newest frame a few hundred times
        q: asyncio.Queue = asyncio.Queue()
        arm.client.follow("st3215/inference", q)
        raw = bytes((await q.get()).Data)
        ts = []
        for _ in range(200):
            t = time.perf_counter(); parse_state(raw); ts.append((time.perf_counter() - t) * 1000)
        summary("2 parse time", ts)
        summary("4 camera frame interval", await camera_rate(arm))
        if len(sys.argv) > 1:
            joint, ticks = sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 40
            if input(f"Nudge {joint} by +/-{ticks} ticks 6 times on bus {arm.follower}? [y/N] ").lower() == "y":
                summary("3 command -> motion", await command_to_motion(arm, joint, ticks))
                await arm.hold()


asyncio.run(main())
