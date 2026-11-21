"""Check a recorded grasp dataset before spending GPU time on it.

Reads NormaCore parquet files (from Station's dataset-generator) and prints one line per
episode: frames, seconds, joints, cameras, image size and what the jaws (j8) did.
Flags what would make a bad training set. Exit code 1 if anything is wrong.

    bash vla/py.sh vla/check_dataset.py vla/data/resistor.parquet
    bash vla/py.sh vla/check_dataset.py vla/data/resistor.parquet --frames-dir vla/data/peek
"""
from __future__ import annotations

import argparse
import io
import sys
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

EXPECT_JOINTS = 8
EXPECT_CAMERAS = 2
JAW = 7  # index of j8 (the jaws) in the joints list


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("parquets", type=Path, nargs="+")
    p.add_argument("--jaw-closed-below", type=float, default=0.5,
                   help="j8 position_norm that counts as closed (ElRobot: open about 0.78, holding 0.22-0.34)")
    p.add_argument("--min-seconds", type=float, default=3.0)
    p.add_argument("--frames-dir", type=Path, help="save the first and last frame of every episode as JPEGs here")
    a = p.parse_args()

    problems: list[str] = []
    n_eps = n_frames = 0
    tasks: Counter = Counter()
    for path in a.parquets:
        t = pq.read_table(path, columns=["episode_start_ns", "timestamp_ns_since_episode_start", "joints", "images", "task"])
        eps = t.column("episode_start_ns").to_pylist()
        ts = t.column("timestamp_ns_since_episode_start").to_pylist()
        joints = t.column("joints").to_pylist()
        task_col = t.column("task").to_pylist()
        tasks.update(task_col)
        print(f"\n{path}  ({t.num_rows} frames)")
        print(f"  {'ep':>3} {'frames':>6} {'sec':>5} {'fps':>5} {'joints':>6} {'cams':>4} {'image':>9}  j8 open→min→end   ok")
        starts = sorted(set(eps), key=eps.index)
        for e_i, start in enumerate(starts):
            idx = [i for i, e in enumerate(eps) if e == start]
            n = len(idx)
            secs = (ts[idx[-1]] - ts[idx[0]]) / 1e9 if n > 1 else 0.0
            fps = (n - 1) / secs if secs > 0 else 0.0
            nj = len(joints[idx[0]])
            imgs = t.column("images")[idx[0]].as_py()
            size = Image.open(io.BytesIO(imgs[0]["jpeg"])).size if imgs else (0, 0)
            jaw = [joints[i][JAW]["position_norm"] for i in idx] if nj > JAW else []
            flags = []
            if nj != EXPECT_JOINTS:
                flags.append(f"{nj} joints")
            if len(imgs) != EXPECT_CAMERAS:
                flags.append(f"{len(imgs)} cameras")
            if secs < a.min_seconds:
                flags.append("too short")
            if jaw and min(jaw) > a.jaw_closed_below:
                flags.append("jaws never close")
            if jaw and jaw[0] < a.jaw_closed_below:
                flags.append("starts with jaws closed")
            ok = "yes" if not flags else "NO: " + ", ".join(flags)
            jaw_txt = f"{jaw[0]:.2f}→{min(jaw):.2f}→{jaw[-1]:.2f}" if jaw else "-"
            print(f"  {e_i:>3} {n:>6} {secs:>5.1f} {fps:>5.1f} {nj:>6} {len(imgs):>4} {size[0]:>4}x{size[1]:<4}  {jaw_txt:<16} {ok}")
            if flags:
                problems.append(f"{path.name} episode {e_i}: {', '.join(flags)}")
            if a.frames_dir:
                a.frames_dir.mkdir(parents=True, exist_ok=True)
                for tag, i in (("first", idx[0]), ("last", idx[-1])):
                    for c, img in enumerate(t.column("images")[i].as_py()):
                        (a.frames_dir / f"{path.stem}-ep{e_i:02d}-{tag}-cam{c}.jpg").write_bytes(img["jpeg"])
        n_eps += len(starts)
        n_frames += t.num_rows

    print(f"\n{n_eps} episodes, {n_frames} frames, tasks: {dict(tasks)}")
    if len(tasks) > 1:
        problems.append("more than one task string; use the same instruction for every grasp")
    if problems:
        print("\nPROBLEMS:")
        for x in problems:
            print("  - " + x)
        return 1
    print("looks good")
    return 0


if __name__ == "__main__":
    sys.exit(main())
