"""Teach and replay named poses (saved in robot/normacore/poses.json, commit it after teaching).

    python3 robot/normacore/examples/07_poses.py list
    python3 robot/normacore/examples/07_poses.py save home      # torque off first, place the arm by hand
    python3 robot/normacore/examples/07_poses.py go home
"""
import asyncio
import json
import sys
from pathlib import Path

from _common import ElRobot

POSES = Path(__file__).resolve().parent.parent / "poses.json"
cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
name = sys.argv[2] if len(sys.argv) > 2 else None


async def main():
    if cmd == "list":
        poses = json.loads(POSES.read_text()) if POSES.exists() else {}
        for k, v in sorted(poses.items()):
            print(f"{k:12s} " + "  ".join(f"{j} {x:.3f}" for j, x in v.items()))
        if not poses:
            print("no poses saved yet")
        return
    if not name:
        raise SystemExit("give a pose name, e.g. home")
    async with await ElRobot.connect() as arm:
        if cmd == "save":
            print(name, await arm.save_pose(name, POSES))
        elif cmd == "go":
            await arm.hold()
            await arm.torque(True)
            print(name, await arm.go_pose(name, POSES))
        else:
            raise SystemExit("use list, save NAME or go NAME")


asyncio.run(main())
