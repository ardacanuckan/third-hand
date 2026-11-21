"""List every servo bus Station sees, to tell the leader from the follower.

Each ElRobot is one bus named by its controller board's serial. Unplug one USB cable and run
this again: the bus that disappears is that arm. Put the serials in robot/normacore/.env.

    python3 robot/normacore/examples/01_list_buses.py
"""
import asyncio

from _common import ElRobot


async def main():
    arm = await ElRobot.connect(require_follower=False)
    for serial, bus in (await arm.buses()).items():
        print(f"\nbus {serial}  port {bus.port}  servos {sorted(bus.motors)}")
        for mid, m in sorted(bus.motors.items()):
            flags = [] if m.calibrated else ["NOT CALIBRATED"]
            if m.overloaded:
                flags.append("OVERLOAD")
            print(f"  j{mid}: norm {m.norm:.3f}  raw {m.raw:4d}  range {m.range_min}-{m.range_max}  "
                  f"torque {'on' if m.torque else 'off'}  {' '.join(flags)}")
    await arm.close()


asyncio.run(main())
