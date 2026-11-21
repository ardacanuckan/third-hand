"""First motion test: move one joint a little and back. Keep a hand on the power switch.

    python3 robot/normacore/examples/03_nudge_joint.py j1 0.05
"""
import asyncio
import sys

from _common import ElRobot


async def main(joint: str, delta: float):
    async with await ElRobot.connect() as arm:
        start = (await arm.joints())[joint]
        target = max(0.0, min(1.0, start + delta))
        if input(f"Move {joint} on bus {arm.follower} from {start:.3f} to {target:.3f} and back? [y/N] ").lower() != "y":
            return
        await arm.torque(True, (joint,))
        print("there:", await arm.move({joint: target}))
        print("back: ", await arm.move({joint: start}))


asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "j1", float(sys.argv[2]) if len(sys.argv) > 2 else 0.05))
