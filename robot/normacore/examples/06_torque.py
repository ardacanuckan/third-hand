"""Torque off to move the arm by hand (teaching), torque on to hold it. Support the arm before switching off.

    python3 robot/normacore/examples/06_torque.py off
    python3 robot/normacore/examples/06_torque.py on
"""
import asyncio
import sys

from _common import ElRobot

on = (sys.argv[1] if len(sys.argv) > 1 else "on").lower() == "on"


async def main():
    async with await ElRobot.connect() as arm:
        if on:
            await arm.hold()  # set goals to where the arm is, so it does not jump when torque returns
        await arm.torque(on)
        print(f"torque {'on' if on else 'off'} on bus {arm.follower}")


asyncio.run(main())
