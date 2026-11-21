"""Feel the handover: release the object when a person pulls on it.

While the arm holds still at the handover pose, a pull shows up in two ways the motor bus reports:
  - current rises in the arm servos (they push back against the pull), and
  - the joints yield a little (the servos' position loop gives way under load).
PullDetector learns a baseline over the first half second, then fires when either signal stays above
its threshold for `hold_s`. A brief touch (shorter than hold_s) does not fire.

    det = PullDetector()
    for each reading: ev = det.update(t, pos_norm, current_ma, ranges)   # -> None or a dict when it fires

On the real arm (Station running, holding the object at the handover pose):
    python3 handover.py --calibrate      # hold still 3 s, then pull 3 times; suggests thresholds
    python3 handover.py --run            # wait for a pull, then open the jaws

Thresholds were tuned on simulated pulls (servo model, 3-10 N). Real current readings may use other
units, so calibrate on the arm first: it writes handover_thresholds.json, which the detector loads.
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARM_JOINTS = ("j1", "j2", "j3", "j4", "j6")       # joints that feel a pull on the gripper (not the jaws, not the rolls)
DEFAULTS = {"current_rise_ma": 150.0, "deflection_deg": 0.8, "hold_s": 0.2, "baseline_s": 0.5}
TICKS_PER_DEG = 4096 / 360


def thresholds() -> dict:
    p = HERE / "handover_thresholds.json"
    return {**DEFAULTS, **(json.loads(p.read_text()) if p.exists() else {})}


class PullDetector:
    def __init__(self, cfg: dict | None = None):
        self.cfg = {**thresholds(), **(cfg or {})}
        self.t0 = None
        self.base_pos: dict[str, list[float]] = {j: [] for j in ARM_JOINTS}
        self.base_cur: dict[str, list[float]] = {j: [] for j in ARM_JOINTS}
        self.ready = False
        self.above_since = None
        self.peak = {"current_ma": 0.0, "deflection_deg": 0.0, "joint": None}

    def signal(self, pos, cur, ranges) -> tuple[float, float, str | None]:
        """(largest current rise mA, largest deflection deg, joint) against the baseline."""
        best_c, best_d, who = 0.0, 0.0, None
        for j in ARM_JOINTS:
            if j not in pos or not self.base_pos[j]:
                continue
            c = abs(cur.get(j, 0.0) - statistics.fmean(self.base_cur[j]))
            r = ranges.get(j, (0, 4096))
            d = abs(pos[j] - statistics.fmean(self.base_pos[j])) * (r[1] - r[0]) / TICKS_PER_DEG
            if c / self.cfg["current_rise_ma"] + d / self.cfg["deflection_deg"] > best_c / self.cfg["current_rise_ma"] + best_d / self.cfg["deflection_deg"]:
                best_c, best_d, who = c, d, j
        return best_c, best_d, who

    def update(self, t: float, pos: dict, cur: dict, ranges: dict | None = None) -> dict | None:
        ranges = ranges or {}
        if self.t0 is None:
            self.t0 = t
        if not self.ready:
            for j in ARM_JOINTS:
                if j in pos:
                    self.base_pos[j].append(pos[j]); self.base_cur[j].append(cur.get(j, 0.0))
            self.ready = t - self.t0 >= self.cfg["baseline_s"]
            return None
        c, d, j = self.signal(pos, cur, ranges)
        if c >= self.cfg["current_rise_ma"] or d >= self.cfg["deflection_deg"]:
            if self.above_since is None:
                self.above_since = t
            if c > self.peak["current_ma"] or d > self.peak["deflection_deg"]:
                self.peak = {"current_ma": round(c), "deflection_deg": round(d, 2), "joint": j}
            if t - self.above_since >= self.cfg["hold_s"]:
                return {"t": t, "pull_started": self.above_since, **self.peak}
        else:
            self.above_since = None
        return None


# ----------------------------------------------------------------------------- real arm

async def wait_for_pull(arm, timeout: float = 15.0, cfg: dict | None = None) -> dict | None:
    """Watch the follower's bus while holding still; return the pull event or None on timeout."""
    import asyncio
    det, loop = PullDetector(cfg), asyncio.get_running_loop()
    t0, seq = loop.time(), -1
    while loop.time() - t0 < timeout:
        if arm._seq != seq and arm.follower in arm._buses:
            seq = arm._seq
            bus = arm._buses[arm.follower]
            pos = {f"j{m}": x.norm for m, x in bus.motors.items()}
            cur = {f"j{m}": float(x.current) for m, x in bus.motors.items()}
            rng = {f"j{m}": (x.range_min, x.range_max) for m, x in bus.motors.items()}
            ev = det.update(loop.time() - t0, pos, cur, rng)
            if ev:
                return ev
        await asyncio.sleep(0.005)
    return None


async def hand_over(arm, timeout: float = 15.0, open_norm: float = 0.6) -> str:
    """Hold still, release on a pull. Returns what happened in words."""
    await arm.hold()
    ev = await wait_for_pull(arm, timeout)
    if ev is None:
        return f"Nobody pulled within {timeout:.0f} s; still holding the object."
    await arm.gripper(open_norm)
    return (f"Felt a pull after {ev['pull_started']:.1f} s ({ev['joint']}: +{ev['current_ma']} mA, "
            f"{ev['deflection_deg']} deg give) and opened the jaws {ev['t'] - ev['pull_started']:.2f} s later.")


async def _calibrate():
    import asyncio, sys
    sys.path.insert(0, str(HERE))
    from elrobot import ElRobot
    async with await ElRobot.connect() as arm:
        await arm.hold()
        print("Hold still: measuring the baseline for 3 s ...")
        rows, loop = [], asyncio.get_running_loop()
        t0, seq = loop.time(), -1
        phase_end = {"still": 3.0, "pull": 15.0}
        print("Then pull on the held object 3 times (1 s each), within 12 s.")
        while loop.time() - t0 < phase_end["pull"]:
            if arm._seq != seq:
                seq = arm._seq
                b = arm._buses[arm.follower]
                rows.append((loop.time() - t0, {f"j{m}": x.norm for m, x in b.motors.items()},
                             {f"j{m}": float(x.current) for m, x in b.motors.items()},
                             {f"j{m}": (x.range_min, x.range_max) for m, x in b.motors.items()}))
            await asyncio.sleep(0.005)
    still = [r for r in rows if r[0] < 3.0]
    det = PullDetector({"baseline_s": 2.5})
    for r in still: det.update(*r)
    noise_c = max(det.signal(r[1], r[2], r[3])[0] for r in still[-10:])
    noise_d = max(det.signal(r[1], r[2], r[3])[1] for r in still[-10:])
    pulls = [det.signal(r[1], r[2], r[3]) for r in rows if r[0] >= 3.0]
    peak_c, peak_d = max(p[0] for p in pulls), max(p[1] for p in pulls)
    cfg = {"current_rise_ma": round(max(3 * noise_c, 0.4 * peak_c), 1), "deflection_deg": round(max(3 * noise_d, 0.4 * peak_d), 2)}
    (HERE / "handover_thresholds.json").write_text(json.dumps(cfg, indent=1))
    print(f"still noise: {noise_c:.0f} mA / {noise_d:.2f} deg; pulls peaked at {peak_c:.0f} mA / {peak_d:.2f} deg")
    print(f"saved handover_thresholds.json: {cfg}")


if __name__ == "__main__":
    import asyncio, sys
    sys.path.insert(0, str(HERE))
    if "--calibrate" in sys.argv:
        asyncio.run(_calibrate())
    elif "--run" in sys.argv:
        from elrobot import ElRobot

        async def main():
            async with await ElRobot.connect() as arm:
                print(await hand_over(arm))
        asyncio.run(main())
    else:
        print(__doc__)
