"""Set safe servo speed/acceleration on the follower before a learned policy drives it.

run_policy.py (norma-core smolvla_py) only writes goal positions, so every servo keeps whatever speed and
acceleration it last had. This writes elrobot.JOINT_PROFILE (gentle shoulder and elbow, quick wrist and
jaws), optionally slowed down for first tests, and leaves the arm holding where it is.

    python3 robot/normacore/vla_train/prepare_arm.py            # profile as is
    python3 robot/normacore/vla_train/prepare_arm.py --slow 0.5 # half speed and acceleration for the first runs
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from elrobot import JOINT_PROFILE, REG_ACC, REG_SPEED, ElRobot, send_commands, sync_write  # noqa: E402


async def main(slow: float) -> None:
    async with await ElRobot.connect() as arm:                  # refuses the leader bus
        bus = await arm.state()
        arm.check_faults(bus)
        ids = {int(j[1:]): p for j, p in JOINT_PROFILE.items()}
        await send_commands(arm.client, [
            sync_write(arm.follower, REG_SPEED, {m: int(p["speed"] * slow).to_bytes(2, "little") for m, p in ids.items()}),
            sync_write(arm.follower, REG_ACC, {m: bytes([max(1, min(254, int(p["acc"] * slow)))]) for m, p in ids.items()}),
        ])
        await arm.torque(True)
        await arm.hold()
        print(f"follower {arm.follower}: speed/acc set from JOINT_PROFILE x {slow}, torque on, holding.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--slow", type=float, default=1.0, help="scale speed and acceleration (0.3-1.0)")
    asyncio.run(main(max(0.1, min(1.0, ap.parse_args().slow))))
