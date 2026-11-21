"""Quality report for recorded episodes before training (needs pyarrow and numpy).

    python check_episodes.py path/to/*.parquet [--frames OUT_DIR]

Per episode: length, frame rate and gaps, idle share, motion range per joint, jaw start, follower lag
behind the leader (goal -> position), peak current. Across episodes: tasks and how much the start pose
varies. --frames saves first/middle/last images of both cameras to eyeball labels against what is seen.
"""
import argparse
import collections
import pathlib

import numpy as np
import pyarrow.parquet as pq


def report(path: pathlib.Path, frames_dir: pathlib.Path | None):
    t = pq.read_table(path, columns=["timestamp_ns_since_episode_start", "joints", "task"]).to_pydict()
    ts = np.array(t["timestamp_ns_since_episode_start"]) / 1e9
    J = t["joints"]
    pos = np.array([[j["position_norm"] for j in fr] for fr in J])
    goal = np.array([[j["goal_norm"] for j in fr] for fr in J])
    cur = np.array([[j["current_ma"] for j in fr] for fr in J])
    dt = np.diff(ts)
    lags = []
    for k in range(pos.shape[1]):
        if np.ptp(goal[:, k]) < 0.05:
            continue
        errs = [np.mean(np.abs(pos[s:, k] - goal[:len(goal) - s, k])) for s in range(8)]
        lags.append(int(np.argmin(errs)))
    still = np.all(np.abs(np.diff(pos, axis=0)) < 0.002, axis=1)
    lead = int(np.argmax(~still)) if (~still).any() else len(still)
    tail = int(np.argmax(~still[::-1])) if (~still).any() else len(still)
    print(f"{path.name}: {len(ts)} frames, {ts[-1]:.1f} s, {1 / np.median(dt):.1f} fps, gaps>200ms {(dt > 0.2).sum()}, "
          f"idle {still.mean() * 100:.0f}% (lead-in {lead / 10:.1f} s, tail {tail / 10:.1f} s), task {set(t['task'])}")
    print("   range: " + " ".join(f"j{k + 1} {np.ptp(pos[:, k]):.2f}" for k in range(pos.shape[1]))
          + f" | jaws start {pos[0, -1]:.2f} | lag {np.median(lags) if lags else 0:.0f} frames | peak {cur.max()} mA")
    if frames_dir:
        imgs = pq.read_table(path, columns=["images"]).to_pydict()["images"]
        for name, i in [("start", 0), ("mid", len(imgs) // 2), ("end", len(imgs) - 1)]:
            for c, im in enumerate(imgs[i]):
                (frames_dir / f"{path.stem}_{name}_cam{c}.jpg").write_bytes(im["jpeg"])
    return pos[0], t["task"][0], len(ts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("parquets", nargs="+", type=pathlib.Path)
    ap.add_argument("--frames", type=pathlib.Path)
    a = ap.parse_args()
    if a.frames:
        a.frames.mkdir(parents=True, exist_ok=True)
    starts, tasks, frames = [], collections.Counter(), 0
    for p in sorted(a.parquets):
        s, task, n = report(p, a.frames)
        starts.append(s); tasks[task] += 1; frames += n
    print(f"\n{len(starts)} episodes, {frames} frames. Episodes per task: {dict(tasks)}")
    print("start-pose spread (std per joint):", np.round(np.std(starts, 0), 3))
    few = [k for k, v in tasks.items() if v < 30]
    if few:
        print(f"Fewer than 30 episodes for: {few}. SmolVLA fine-tunes usually need 30-50+ per task.")
