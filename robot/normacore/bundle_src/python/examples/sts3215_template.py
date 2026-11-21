"""Template for driving Feetech STS3215 servos directly (e.g. with the `scservo_sdk` / `st3215` libraries).

Fill in the three functions marked TODO for your bus library and calibration. The character logic is
untouched: the planner already gives STS3215 register values for acceleration (0x29) and speed (0x2E).
Teach a 'neutral' pose first (arm upright, clear) and pass it to plan(): every move stays a small
offset from it.

Safety: keep a hand on the power switch for the first runs; joints may move the other way on your
arm (flip them in characters.json limits.sign).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from thc import Library, play, units  # noqa: E402

SERVO_ID = {"j1": 1, "j2": 2, "j3": 3, "j4": 4, "j5": 5, "j6": 6, "j7": 7, "j8": 8}
CALIBRATION = {}   # TODO: {"j1": (range_min_ticks, range_max_ticks), ...} from your calibration


def write_registers(servo_id: int, acc: int, speed: int, goal_ticks: int) -> None:
    """TODO: write acc (0x29, 1 byte), speed (0x2E, 2 bytes) and goal position (0x2A, 2 bytes).
    Better: one sync-write per register for all joints of a step, so they start together."""
    raise NotImplementedError


def read_position_ticks(servo_id: int) -> int:
    """TODO: read present position (0x38, 2 bytes)."""
    raise NotImplementedError


def send(goals, acc, speed):
    for j, v in goals.items():
        lo, hi = CALIBRATION[j]
        write_registers(SERVO_ID[j], acc[j], speed[j], units.norm_to_ticks(v, lo, hi))


def read():
    out = {}
    for j, sid in SERVO_ID.items():
        lo, hi = CALIBRATION[j]
        out[j] = (read_position_ticks(sid) - lo) / (hi - lo)
    return out


if __name__ == "__main__":
    lib = Library.load()
    neutral = read()                                 # or a taught pose: {joint: 0..1}
    play(lib.plan("butler", "bow", neutral=neutral), send, read)
