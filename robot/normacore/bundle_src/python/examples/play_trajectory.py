"""Stream a pre-computed trajectory (radians, 30 fps) to a robot that takes position targets only.

    cd python && python3 examples/play_trajectory.py smooth/air_kiss
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thc import trajectories  # noqa: E402


def set_joint_targets(q: dict) -> None:
    """TODO: your robot's 'go to these joint angles (rad)' call. Printing every 10th frame here."""
    if int(time.monotonic() * 30) % 10 == 0:
        print("  " + " ".join(f"{j} {v:+.3f}" for j, v in q.items()))


if __name__ == "__main__":
    clip = sys.argv[1] if len(sys.argv) > 1 else "smooth/air_kiss"
    info = trajectories.load()[clip]
    print(f"{clip}: {len(info['q'])} frames, shoulder peak {info['peak_shoulder']} % of stall")
    t0 = time.monotonic()
    for t, q in trajectories.frames(clip):
        time.sleep(max(0.0, t0 + t - time.monotonic()))
        set_joint_targets(q)
