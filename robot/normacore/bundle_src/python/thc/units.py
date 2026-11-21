"""Unit conversions for robots that are not driven in STS3215 register units.

Positions in this package are normalized 0..1 inside each joint's calibrated range. To get radians you
need that range on YOUR arm; the ElRobot URDF limits (characters.json joints.urdf_limits_rad) are a good
default if your calibration spans the full joint range.
"""
import math

TICK_RAD = 2 * math.pi / 4096           # one STS3215 encoder tick


def acc_to_rad_s2(acc: int) -> float:
    """STS3215 acceleration register value -> rad/s^2 (0 means 'no ramp' on the servo)."""
    return acc * 100 * TICK_RAD


def speed_to_rad_s(speed: int) -> float:
    """STS3215 speed register value (ticks/s) -> rad/s."""
    return speed * TICK_RAD


def norm_to_rad(v: float, lo: float, hi: float) -> float:
    """Normalized position -> radians, given the joint's calibrated [lo, hi] in radians."""
    return lo + v * (hi - lo)


def rad_to_norm(q: float, lo: float, hi: float) -> float:
    return (q - lo) / (hi - lo)


def norm_to_ticks(v: float, range_min: int, range_max: int) -> int:
    """Normalized position -> raw STS3215 goal ticks inside the calibrated range."""
    return int(round(range_min + max(0.0, min(1.0, v)) * (range_max - range_min)))
