"""Save camera frames (and the arm's joints) for calibration or a vision dataset.

    python3 robot/normacore/calibration/capture.py --tag side            # Enter = take a shot, q = quit
    python3 robot/normacore/calibration/capture.py --tag wrist --every 1 # one shot per second, Ctrl+C stops

Writes captures/<tag>/<n>_cam<i>.jpg plus <n>.json (joints, time). Which camera is which: the
wrist camera's image shows the jaws. Needs Station running (run_station.sh) but no OpenCV.
"""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from elrobot import ElRobot  # noqa: E402


async def shoot(arm: ElRobot, out: Path, n: int) -> str:
    frames = await arm.frames()
    try:
        joints = await arm.joints()
    except Exception:                       # cameras still work if the motor bus is busy
        joints = {}
    for i, jpeg in enumerate(frames):
        (out / f"{n:04d}_cam{i}.jpg").write_bytes(jpeg)
    (out / f"{n:04d}.json").write_text(json.dumps({"time": time.time(), "joints": joints, "cameras": len(frames)}))
    return f"#{n}: {len(frames)} camera(s), {sum(len(f) for f in frames) // 1024} KB"


async def main(tag: str, every: float | None) -> None:
    out = HERE / "captures" / tag
    out.mkdir(parents=True, exist_ok=True)
    n = len(list(out.glob("*.json")))
    async with await ElRobot.connect(require_follower=False) as arm:
        print(f"Saving to {out}. " + ("Ctrl+C to stop." if every else "Enter = shot, q + Enter = quit."))
        while True:
            if every:
                print(await shoot(arm, out, n)); n += 1
                await asyncio.sleep(every)
            else:
                key = await asyncio.to_thread(input, "> ")
                if key.strip().lower() == "q":
                    break
                print(await shoot(arm, out, n)); n += 1
    print(f"{n} shots in {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="folder name: side, wrist, mat, dataset_...")
    ap.add_argument("--every", type=float, help="seconds between automatic shots")
    a = ap.parse_args()
    try:
        asyncio.run(main(a.tag, a.every))
    except KeyboardInterrupt:
        print("stopped")
