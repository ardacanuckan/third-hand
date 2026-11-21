"""Default control library for NormaCore's ElRobot through Station (v0.1.0-beta.10).

Built on norma-core's own station_py client and examples (vendored in ./vendor, MIT) and on
the lessons of the June 2026 NormaCore-track team (github.com/manas-arumalla/norma-robot, MIT).

    import asyncio
    from elrobot import ElRobot

    async def main():
        async with await ElRobot.connect() as arm:   # FOLLOWER_SERIAL from .env, or the only bus
            print(await arm.joints())                 # {"j1": 0.51, ..., "j8": 0.78}
            await arm.move({"j1": 0.55})              # small, overload-safe steps
            await arm.gripper(0.78)                   # open the jaws

    asyncio.run(main())

Joint values are Station's normalized position (0..1 inside each servo's calibrated range).
j1..j8 are servo ids 1..8: j7 rotates the gripper, j8 opens and closes the jaws.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENDOR = Path(os.environ.get("NORMA_CORE_ROOT", HERE / "vendor"))
for _p in (VENDOR, VENDOR / "software" / "station" / "shared"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from station_py import new_station_client, send_commands  # noqa: E402
from target.gen_python.protobuf.drivers.inferences import normvla  # noqa: E402
from target.gen_python.protobuf.drivers.st3215 import st3215  # noqa: E402
from target.gen_python.protobuf.station import commands, drivers  # noqa: E402

log = logging.getLogger("elrobot")

ST3215_QUEUE = "st3215/inference"
NORMVLA_QUEUE = "inference/normvla"
JOINTS = ("j1", "j2", "j3", "j4", "j5", "j6", "j7", "j8")
JAWS_OPEN = 0.78  # j8 position_norm reported by the June team; check on your arm

# ST3215 registers (norma-core examples/st3215-remote-teleop-py/state.py; status per the Feetech STS map)
REG_TORQUE = 0x28
REG_ACC = 0x29
REG_GOAL = 0x2A
REG_SPEED = 0x2E
REG_POS = 0x38
REG_STATUS = 0x41
REG_CURRENT = 0x45
OVERLOAD_BIT = 0x20
SAFETY_MARGIN = 20  # raw ticks kept away from each calibrated end stop


class RobotError(RuntimeError):
    """Something the caller must handle: no bus, wrong bus, overload, timeout."""


def load_env(path: Path = HERE / ".env") -> None:
    """Read KEY=VALUE lines from robot/normacore/.env into os.environ (existing values win)."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


# ----------------------------------------------------------------------------- state parsing

@dataclass
class Motor:
    id: int
    raw: int
    range_min: int
    range_max: int
    torque: bool
    status: int
    current: int

    @property
    def norm(self) -> float:
        if self.range_max <= self.range_min:
            return 0.0
        return round((self.raw - self.range_min) / (self.range_max - self.range_min), 4)

    @property
    def overloaded(self) -> bool:
        return bool(self.status & OVERLOAD_BIT)

    @property
    def calibrated(self) -> bool:
        return self.range_max > self.range_min


@dataclass
class Bus:
    serial: str
    port: str
    motors: dict[int, Motor] = field(default_factory=dict)
    received: float = 0.0  # time.monotonic() when this frame arrived


def _u8(b: bytes, a: int) -> int:
    return b[a] if len(b) > a else 0


def _u16(b: bytes, a: int) -> int:
    return struct.unpack_from("<H", b, a)[0] if len(b) >= a + 2 else 0


def _position(raw: int) -> int:
    """ST3215 positions carry a sign bit; fold them into 0..4095 like norma-core does."""
    return (4096 - (raw & 4095)) & 4095 if raw & 0x8000 else raw & 4095


def _text(v) -> str:
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v).decode("utf-8", "replace")
    return "" if v is None else str(v)


def parse_state(data: bytes) -> dict[str, Bus]:
    """Decode one st3215/inference entry into {bus serial: Bus}."""
    st = st3215.InferenceStateReader(memoryview(data))
    now = time.monotonic()
    out: dict[str, Bus] = {}
    for bs in st.get_buses() or []:
        info = bs.get_bus()
        if not info:
            continue
        bus = Bus(serial=_text(info.get_serial_number()), port=_text(info.get_port_name()), received=now)
        for m in bs.get_motors() or []:
            s = bytes(m.get_state() or b"")
            mid = int(m.get_id())
            bus.motors[mid] = Motor(
                id=mid, raw=_position(_u16(s, REG_POS)), range_min=int(m.get_range_min()),
                range_max=int(m.get_range_max()), torque=_u8(s, REG_TORQUE) != 0,
                status=_u8(s, REG_STATUS), current=_u16(s, REG_CURRENT),
            )
        out[bus.serial] = bus
    return out


# ----------------------------------------------------------------------------- commands

def norm_to_raw(norm: float, range_min: int, range_max: int) -> int:
    lo, hi = range_min + SAFETY_MARGIN, range_max - SAFETY_MARGIN
    if hi <= lo:
        lo, hi = range_min, range_max
    raw = int(round(range_min + max(0.0, min(1.0, float(norm))) * (range_max - range_min)))
    return max(lo, min(hi, raw))


def sync_write(bus_serial: str, address: int, values: dict[int, bytes]) -> commands.DriverCommand:
    """One ST3215 sync-write: the same register on several motors in one packet."""
    cmd = st3215.Command(
        target_bus_serial=bus_serial,
        sync_write=st3215.ST3215SyncWriteCommand(
            address=address,
            motors=[st3215.ST3215SyncWriteCommand_MotorWrite(motor_id=mid, value=val) for mid, val in values.items()],
        ),
    )
    return commands.DriverCommand(type=drivers.StationCommandType.STC_ST3215_COMMAND, body=cmd.encode())


def _jid(name: str) -> int:
    if name not in JOINTS:
        raise ValueError(f"unknown joint {name!r}; use one of {', '.join(JOINTS)}")
    return int(name[1:])


# ----------------------------------------------------------------------------- the robot

class ElRobot:
    """One ElRobot follower arm through Station. Create it with `await ElRobot.connect()`."""

    def __init__(self, client, follower: str | None):
        self.client = client
        self.follower = follower
        self._buses: dict[str, Bus] = {}
        self._seq = 0
        self._pump_task: asyncio.Task | None = None

    # -- connection

    @classmethod
    async def connect(cls, host: str | None = None, follower: str | None = None,
                      require_follower: bool = True, timeout: float = 10.0) -> "ElRobot":
        load_env()
        host = host or os.environ.get("STATION_HOST", "localhost")
        follower = follower or os.environ.get("FOLLOWER_SERIAL") or None
        try:
            client = await new_station_client(host, log)
        except Exception as e:  # noqa: BLE001
            raise RobotError(f"cannot reach Station at {host}:8888 ({e}). Is it running with --tcp?") from e
        robot = cls(client, follower)
        robot._pump_task = asyncio.create_task(robot._pump())
        buses = await robot.buses(timeout)
        if not require_follower:
            return robot
        leader = os.environ.get("LEADER_SERIAL") or None
        if robot.follower is None:
            candidates = [s for s in buses if s != leader]
            if len(candidates) != 1:
                raise RobotError(f"found buses {list(buses)}; set FOLLOWER_SERIAL in robot/normacore/.env")
            robot.follower = candidates[0]
            log.warning("using the only bus %s as the follower; set FOLLOWER_SERIAL to make it explicit", robot.follower)
        if robot.follower == leader:
            raise RobotError("FOLLOWER_SERIAL equals LEADER_SERIAL; refusing to command the leader arm")
        if robot.follower not in buses:
            raise RobotError(f"follower {robot.follower} not found; Station sees {list(buses)}")
        return robot

    async def __aenter__(self) -> "ElRobot":
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def close(self) -> None:
        if self._pump_task:
            self._pump_task.cancel()
        try:
            self.client.close_connection()
        except Exception:  # noqa: BLE001
            pass

    async def _pump(self) -> None:
        """Keep the latest motor-bus state. Camera-independent, so it never freezes with the video feed."""
        q: asyncio.Queue = asyncio.Queue()
        self.client.follow(ST3215_QUEUE, q)
        while True:
            entry = await q.get()
            if entry is None:
                log.error("%s stream closed", ST3215_QUEUE)
                return
            try:
                self._buses = parse_state(bytes(entry.Data))
                self._seq += 1
            except Exception as e:  # noqa: BLE001
                log.warning("could not parse a %s entry: %s", ST3215_QUEUE, e)

    async def _fresh(self, timeout: float) -> dict[str, Bus]:
        start, deadline = self._seq, time.monotonic() + timeout
        while self._seq == start:
            if time.monotonic() > deadline:
                raise RobotError(f"no motor-bus update from Station for {timeout:.1f} s")
            await asyncio.sleep(0.005)
        return self._buses

    # -- reading

    async def buses(self, timeout: float = 5.0) -> dict[str, Bus]:
        """Every servo bus Station sees, by serial."""
        return dict(await self._fresh(timeout))

    async def state(self, timeout: float = 2.0) -> Bus:
        buses = await self._fresh(timeout)
        bus = buses.get(self.follower or "")
        if bus is None:
            raise RobotError(f"follower bus {self.follower} missing from the latest frame")
        return bus

    async def joints(self) -> dict[str, float]:
        """Current j1..j8 in position_norm, read from the motor bus."""
        bus = await self.state()
        return {f"j{mid}": bus.motors[mid].norm for mid in sorted(bus.motors) if f"j{mid}" in JOINTS}

    @staticmethod
    def check_faults(bus: Bus) -> None:
        bad = [f"j{m.id}" for m in bus.motors.values() if m.overloaded]
        if bad:
            raise RobotError(f"overload on {', '.join(bad)}: power-cycle the follower, then home() in small steps")

    # -- writing

    async def torque(self, on: bool, joints: tuple[str, ...] = JOINTS) -> None:
        """Torque off lets you move the arm by hand (for teaching poses). Torque on holds it."""
        cmd = sync_write(self.follower, REG_TORQUE, {_jid(j): bytes([1 if on else 0]) for j in joints})
        await send_commands(self.client, [cmd])

    async def _goals(self, bus: Bus, goals: dict[int, float]) -> None:
        values = {}
        for mid, g in goals.items():
            m = bus.motors.get(mid)
            if m is None or not m.calibrated:
                raise RobotError(f"j{mid} is missing or not calibrated; run Auto Calibrate in the Station web UI")
            values[mid] = norm_to_raw(g, m.range_min, m.range_max).to_bytes(2, "little")
        await send_commands(self.client, [sync_write(self.follower, REG_GOAL, values)])

    async def move(self, targets: dict[str, float], *, step: float = 0.04, dt: float = 0.12,
                   speed: int = 600, acc: int = 20, tol: float = 0.015, timeout: float = 6.0) -> dict[str, float]:
        """Move joints to targets (0..1) in small steps so the shoulder never takes the full load at once.

        Lift with the elbow (j3) tucked first and the shoulder (j2) second; send those as two moves.
        """
        goal = {_jid(j): max(0.0, min(1.0, float(v))) for j, v in targets.items()}
        bus = await self.state()
        self.check_faults(bus)
        start = {mid: bus.motors[mid].norm for mid in goal}
        await send_commands(self.client, [
            sync_write(self.follower, REG_SPEED, {mid: int(speed).to_bytes(2, "little") for mid in goal}),
            sync_write(self.follower, REG_ACC, {mid: bytes([max(0, min(254, int(acc)))]) for mid in goal}),
        ])
        n = max(1, math.ceil(max(abs(goal[m] - start[m]) for m in goal) / step))
        for i in range(1, n + 1):
            await self._goals(bus, {m: start[m] + (goal[m] - start[m]) * i / n for m in goal})
            await asyncio.sleep(dt)
            self.check_faults(self._buses.get(self.follower, bus))
        deadline = time.monotonic() + timeout
        while True:
            bus = await self.state()
            self.check_faults(bus)
            now = {m: bus.motors[m].norm for m in goal}
            if all(abs(now[m] - goal[m]) <= tol for m in goal) or time.monotonic() > deadline:
                if time.monotonic() > deadline:
                    log.warning("move ended off target: %s", {f"j{m}": round(now[m] - goal[m], 3) for m in goal})
                return {f"j{m}": now[m] for m in goal}
            await asyncio.sleep(0.05)

    async def gripper(self, norm: float, **kw) -> dict[str, float]:
        """Open or close the jaws (j8). Open is about JAWS_OPEN; smaller values close."""
        return await self.move({"j8": norm}, step=kw.pop("step", 0.1), **kw)

    async def hold(self) -> None:
        """Stop where the arm is now: set every goal to the current position."""
        bus = await self.state()
        await self._goals(bus, {mid: m.norm for mid, m in bus.motors.items() if m.calibrated})

    # -- cameras

    async def frames(self, timeout: float = 3.0) -> list[bytes]:
        """Latest camera JPEGs (one per camera) from the inference/normvla bridge."""
        qr = self.client.read_from_tail(NORMVLA_QUEUE, offset=b"\x00", limit=1, step=1, buf_size=1)
        try:
            entry = await asyncio.wait_for(qr.data.get(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise RobotError(f"no frame on {NORMVLA_QUEUE}; check the inference section of station.yaml") from e
        if entry is None:
            raise RobotError(f"{NORMVLA_QUEUE} is empty (err={qr.err})")
        frame = normvla.FrameReader(memoryview(bytes(entry.Data)))
        return [bytes(im.get_jpeg()) for im in (frame.get_images() or [])]

    # -- poses

    async def save_pose(self, name: str, path: Path = HERE / "poses.json") -> dict[str, float]:
        poses = json.loads(path.read_text()) if path.exists() else {}
        poses[name] = await self.joints()
        path.write_text(json.dumps(poses, indent=2, sort_keys=True) + "\n")
        return poses[name]

    async def go_pose(self, name: str, path: Path = HERE / "poses.json", **kw) -> dict[str, float]:
        poses = json.loads(path.read_text()) if path.exists() else {}
        if name not in poses:
            raise KeyError(f"no pose {name!r} in {path.name}; saved: {', '.join(sorted(poses)) or 'none'}")
        return await self.move(poses[name], **kw)
