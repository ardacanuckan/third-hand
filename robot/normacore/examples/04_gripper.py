"""Open or close the jaws (j8).

    python3 robot/normacore/examples/04_gripper.py open
    python3 robot/normacore/examples/04_gripper.py close
    python3 robot/normacore/examples/04_gripper.py 0.5
"""
import asyncio
import sys

from _common import JAWS_OPEN, ElRobot

arg = sys.argv[1] if len(sys.argv) > 1 else "open"
value = {"open": JAWS_OPEN, "close": 0.25}.get(arg)
value = float(arg) if value is None else value


async def main():
    async with await ElRobot.connect() as arm:
        await arm.torque(True, ("j8",))
        print(await arm.gripper(value))


asyncio.run(main())
