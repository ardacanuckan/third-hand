"""Write a small synthetic dataset in NormaCore's parquet format, to test the pipeline without the arm.

Same schema that Station's dataset-generator writes (docs/datasets/export-parquet in norma-core):
episode_start_ns, global_frame_id, timestamp_ns_since_episode_start, joints (8 ST3215 servos),
images (table and wrist camera JPEGs, 224 x 224), task. Each episode moves down, closes the
jaws (j8) and lifts, at 10 frames per second.

    bash vla/py.sh vla/make_fake_dataset.py --episodes 6 --output vla/data/fake.parquet
"""
from __future__ import annotations

import argparse
import io
import math
import random
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
from PIL import Image, ImageDraw

TASK = "pick up the resistor below the gripper"
RANGE = (900, 3200)  # raw servo ticks for every joint, roughly a calibrated ST3215 range
JAW_OPEN, JAW_CLOSED = 0.78, 0.30

JOINT_TYPE = pa.struct([
    ("range_min", pa.uint32()), ("range_max", pa.uint32()), ("position", pa.uint32()),
    ("position_norm", pa.float32()), ("goal", pa.uint32()), ("goal_norm", pa.float32()),
    ("current_ma", pa.uint32()), ("velocity", pa.uint32()),
])
SCHEMA = pa.schema([
    ("episode_start_ns", pa.uint64()), ("global_frame_id", pa.binary()),
    ("timestamp_ns_since_episode_start", pa.uint64()), ("joints", pa.list_(JOINT_TYPE)),
    ("images", pa.list_(pa.struct([("jpeg", pa.binary())]))), ("task", pa.string()),
])


def jpeg(draw_fn) -> bytes:
    im = Image.new("RGB", (224, 224), (232, 232, 228))
    draw_fn(ImageDraw.Draw(im))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def resistor(d: ImageDraw.ImageDraw, cx: float, cy: float, scale: float) -> None:
    w, h = 28 * scale, 9 * scale
    d.line([(cx - 2.2 * w, cy), (cx + 2.2 * w, cy)], fill=(150, 150, 150), width=max(1, int(2 * scale)))
    d.rounded_rectangle([cx - w, cy - h, cx + w, cy + h], radius=h, fill=(222, 196, 150))
    for i, c in enumerate([(120, 70, 30), (40, 140, 60), (120, 70, 30), (200, 160, 40)]):
        x = cx - w * 0.6 + i * w * 0.38
        d.rectangle([x, cy - h, x + w * 0.16, cy + h], fill=c)


def episode(ep: int, frames: int, rng: random.Random):
    off_x, off_y = rng.uniform(-12, 12), rng.uniform(-8, 8)
    hover = [0.5 + rng.uniform(-0.05, 0.05) for _ in range(7)]
    rows = []
    for f in range(frames):
        t = f / (frames - 1)
        down = min(1.0, t / 0.4)                       # 0–40 %: descend
        close = min(1.0, max(0.0, (t - 0.4) / 0.2))    # 40–60 %: close the jaws
        lift = max(0.0, (t - 0.6) / 0.4)               # 60–100 %: lift
        pos = [hover[0], hover[1] + 0.08 * down - 0.06 * lift, hover[2] - 0.06 * down + 0.05 * lift,
               hover[3] + 0.03 * down, hover[4], hover[5] - 0.02 * down, hover[6],
               JAW_OPEN + (JAW_CLOSED - JAW_OPEN) * close]
        nxt = min(1.0, (f + 1) / (frames - 1))
        goal = [p + 0.004 * math.sin(nxt * 6 + i) for i, p in enumerate(pos)]
        goal[7] = JAW_OPEN + (JAW_CLOSED - JAW_OPEN) * min(1.0, max(0.0, (nxt - 0.4) / 0.2))
        lo, hi = RANGE
        joints = [{"range_min": lo, "range_max": hi, "position": int(lo + p * (hi - lo)), "position_norm": p,
                   "goal": int(lo + g * (hi - lo)), "goal_norm": g, "current_ma": 40 + int(300 * close * (i == 7)),
                   "velocity": 0} for i, (p, g) in enumerate(zip(pos, goal))]
        table = jpeg(lambda d: (resistor(d, 112 + off_x, 120 + off_y - 30 * lift, 0.5),
                                d.ellipse([100 + off_x, 60 - 40 * down, 124 + off_x, 84 - 40 * down], fill=(60, 60, 70))))
        wrist = jpeg(lambda d: (resistor(d, 112 + off_x * (1 - down), 112 + off_y * (1 - down), 1.0 + down),
                                d.rectangle([60 + 40 * close, 180, 90 + 40 * close, 224], fill=(90, 90, 95)),
                                d.rectangle([134 - 40 * close, 180, 164 - 40 * close, 224], fill=(90, 90, 95))))
        rows.append({"joints": joints, "images": [{"jpeg": table}, {"jpeg": wrist}],
                     "timestamp_ns_since_episode_start": f * 100_000_000})
    return rows


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--episodes", type=int, default=6)
    p.add_argument("--frames", type=int, default=60, help="frames per episode (10 per second)")
    p.add_argument("--output", type=Path, default=Path("vla/data/fake.parquet"))
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    rng = random.Random(a.seed)
    cols = {k: [] for k in SCHEMA.names}
    t0, fid = 1_795_000_000_000_000_000, 0
    for ep in range(a.episodes):
        start = t0 + ep * 20_000_000_000
        for r in episode(ep, a.frames, rng):
            fid += 1
            cols["episode_start_ns"].append(start)
            cols["global_frame_id"].append(fid.to_bytes(8, "little"))
            cols["timestamp_ns_since_episode_start"].append(r["timestamp_ns_since_episode_start"])
            cols["joints"].append(r["joints"])
            cols["images"].append(r["images"])
            cols["task"].append(TASK)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(cols, schema=SCHEMA), a.output, compression="snappy")
    print(f"wrote {a.output}: {a.episodes} episodes x {a.frames} frames, 8 joints, 2 cameras")


if __name__ == "__main__":
    main()
