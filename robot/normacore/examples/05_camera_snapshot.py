"""Save the latest frame from each camera as JPEG into robot/normacore/snapshots/.

Needs the inference/normvla section of station.yaml (pinned to the follower serial when the leader
is also connected). Which file is the wrist camera? The one that shows the jaws.

    python3 robot/normacore/examples/05_camera_snapshot.py
"""
import asyncio
import time
from pathlib import Path

from _common import ElRobot

out = Path(__file__).resolve().parent.parent / "snapshots"


async def main():
    async with await ElRobot.connect() as arm:
        frames = await arm.frames()
        out.mkdir(exist_ok=True)
        stamp = time.strftime("%H%M%S")
        for i, jpeg in enumerate(frames):
            p = out / f"cam{i}_{stamp}.jpg"
            p.write_bytes(jpeg)
            print(f"saved {p} ({len(jpeg) // 1024} KB)")


asyncio.run(main())
