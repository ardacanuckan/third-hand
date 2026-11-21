"""Run a character on a pretend robot that prints what it receives. Start here, then replace send().

    cd python && python3 examples/play_fake_robot.py trickster kick_ball
    python3 examples/play_fake_robot.py --list
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thc import Library, play, units  # noqa: E402

lib = Library.load()
LIMITS = lib.data["joints"]["urdf_limits_rad"]     # replace with YOUR arm's calibrated ranges (radians)


def send(goals, acc, speed):
    """Called once per step. goals: {joint: 0..1}; acc/speed: STS3215 units per joint."""
    parts = []
    for j, v in sorted(goals.items()):
        rad = units.norm_to_rad(v, *LIMITS[j])
        parts.append(f"{j} {rad:+.3f} rad (acc {units.acc_to_rad_s2(acc[j]):.0f} rad/s², max {units.speed_to_rad_s(speed[j]):.1f} rad/s)")
    print("  " + " | ".join(parts))


if __name__ == "__main__":
    if "--list" in sys.argv or len(sys.argv) < 3:
        print("characters:", ", ".join(lib.characters))
        print("gestures:  ", ", ".join(g for g in lib.moves if g not in lib.scenes))
        print("scenes:    ", ", ".join(lib.scenes))
        sys.exit(0)
    name, move = sys.argv[1], sys.argv[2]
    c = lib.characters[name]
    print(f"{name}: {c.archetype} [{c.laban}] performs {move}")
    play(lib.plan(name, move), send)                # no read(): bound steps wait an estimated move time
