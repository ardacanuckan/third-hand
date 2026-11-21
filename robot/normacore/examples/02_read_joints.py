"""Print the follower's joints five times a second. Move the arm by hand (torque off) to see them change.

    python3 robot/normacore/examples/02_read_joints.py [seconds]
"""
import asyncio
import sys
import time

from _common import ElRobot


async def main(seconds: float):
    async with await ElRobot.connect() as arm:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            j = await arm.joints()
            print("  ".join(f"{k} {v:.3f}" for k, v in j.items()))
            await asyncio.sleep(0.2)


asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 10))
