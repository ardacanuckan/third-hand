"""Tests for the policy grasp control loop against a fake Station, with no arm and no model.

    bash vla/py.sh vla/test_policy_grasp.py

A fake client serves normvla frames from a tiny simulated arm (each joint moves halfway to its
last goal per frame) and decodes every sync-write the loop sends. Fake policies script the
model's output, so the stop rules and safety checks can be checked one by one.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "robot" / "normacore"))
sys.path.insert(0, str(HERE))

import elrobot  # noqa: E402,F401  (vendored station_py and protobuf paths)
import station_py  # noqa: E402
from target.gen_python.protobuf.drivers.inferences import normvla  # noqa: E402
from target.gen_python.protobuf.drivers.st3215 import st3215  # noqa: E402

import policy_grasp as pg  # noqa: E402

RMIN, RMAX, N = 1000, 3000, 8
FOLLOWER, LEADER = "FOLLOW01", "LEADER01"


class FakeArm:
    def __init__(self):
        self.pos = [0.5] * 7 + [0.78]          # jaws open
        self.goal = list(self.pos)
        self.sent: list[dict[int, int]] = []
        self.fid = 0

    def frame_bytes(self) -> bytes:
        self.pos = [p + 0.5 * (g - p) for p, g in zip(self.pos, self.goal)]
        self.fid += 1
        joints = [normvla.Joint(range_min=RMIN, range_max=RMAX, position=int(RMIN + p * (RMAX - RMIN)), position_norm=p,
                                goal=int(RMIN + g * (RMAX - RMIN)), goal_norm=g) for p, g in zip(self.pos, self.goal)]
        jpg = bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffdb")  # never decoded by the fake policy
        return normvla.Frame(global_frame_id=self.fid.to_bytes(8, "little"), joints=joints,
                             images=[normvla.Image(jpeg=jpg), normvla.Image(jpeg=jpg)]).encode()

    def apply(self, cmd) -> None:
        c = st3215.CommandReader(memoryview(cmd.body))
        assert c.get_target_bus_serial() == FOLLOWER, "command went to the wrong bus"
        sw = c.get_sync_write()
        assert sw.get_address() == pg.REG_GOAL
        raws = {m.get_motor_id(): int.from_bytes(bytes(m.get_value()), "little") for m in sw.get_motors()}
        self.sent.append(raws)
        for mid, raw in raws.items():
            self.goal[mid - 1] = (raw - RMIN) / (RMAX - RMIN)


class FakeClient:
    def __init__(self, arm: FakeArm):
        self.arm = arm

    def read_from_tail(self, queue, offset, limit, step, buf_size):
        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(SimpleNamespace(Data=self.arm.frame_bytes()))
        return SimpleNamespace(data=q, err=None)


class ScriptedPolicy:
    """Stands in for GraspPolicy: fn(state) -> next goal row; repeated over a 50-step chunk."""
    def __init__(self, fn):
        self.fn, self.n_joints, self.image_keys = fn, N, ("cam0", "cam1")

    def predict(self, state, jpegs):
        return np.tile(np.asarray(self.fn(state), dtype=np.float32), (50, 1))


def close_jaws(state):
    g = list(state)
    g[7] = max(0.25, state[7] - 0.04)  # 80 ticks a step on this fake range: under the 100-tick limit
    return g


def run(policy, **kw):
    arm = FakeArm()
    client = FakeClient(arm)

    async def fake_send(_client, cmds):
        for c in cmds:
            arm.apply(c)
    station_py.send_commands = fake_send
    cfg = pg.GraspConfig(bus_serial=kw.pop("bus", FOLLOWER), rate_hz=200, min_seconds=0.0, **kw)
    stop = kw.pop("stop", None)
    return asyncio.run(pg.policy_grasp(client, policy, cfg, stop)), arm


def test_grasp_finishes_when_jaws_settle():
    res, arm = run(ScriptedPolicy(close_jaws))
    assert res["ok"] and res["reason"] == "jaws closed", res
    assert res["jaw"] < 0.45 and res["steps"] > 3
    last = arm.sent[-1]
    assert sorted(last) == list(range(1, 9)), "every command must cover all 8 motors"


def test_big_jump_aborts_and_holds():
    res, arm = run(ScriptedPolicy(lambda s: [min(1.0, s[0] + 0.4)] + list(s[1:])), max_delta_ticks=100)
    assert not res["ok"] and res["reason"].startswith("aborted"), res
    assert res["steps"] == 0, "nothing may be sent before the check"
    hold = arm.sent[-1]
    assert abs(hold[1] - int(RMIN + 0.5 * (RMAX - RMIN))) <= 1, "the arm must hold where it is"


def test_goals_stay_inside_the_safety_margin():
    res, arm = run(ScriptedPolicy(lambda s: [1.0] * 7 + [0.0]), max_delta_ticks=0, timeout_s=0.2)
    for cmd in arm.sent:
        for raw in cmd.values():
            assert RMIN + pg.SAFETY_MARGIN <= raw <= RMAX - pg.SAFETY_MARGIN, raw


def test_timeout_when_jaws_never_close():
    res, _ = run(ScriptedPolicy(lambda s: list(s)), timeout_s=0.3)
    assert not res["ok"] and res["reason"] == "timeout", res


def test_refuses_the_leader():
    os.environ["LEADER_SERIAL"] = LEADER
    try:
        run(ScriptedPolicy(close_jaws), bus=LEADER)
    except RuntimeError as e:
        assert "leader" in str(e)
    else:
        raise AssertionError("commanding the leader must fail")
    finally:
        del os.environ["LEADER_SERIAL"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"ok  {t.__name__}")
    print(f"{len(tests)} passed")
