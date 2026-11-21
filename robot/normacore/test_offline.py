"""Offline checks for elrobot.py: no Station or robot needed.

    python3 robot/normacore/test_offline.py

Builds Station messages with the vendored protobuf classes and checks that elrobot decodes
state and encodes commands the way Station expects.
"""
import struct

from elrobot import (OVERLOAD_BIT, REG_GOAL, REG_POS, REG_STATUS, REG_TORQUE, SAFETY_MARGIN, norm_to_raw,
                     parse_state, st3215, sync_write)


def motor_state(raw_pos: int, torque: int = 1, status: int = 0) -> bytes:
    b = bytearray(0x50)
    struct.pack_into("<H", b, REG_POS, raw_pos)
    b[REG_TORQUE] = torque
    b[REG_STATUS] = status
    return bytes(b)


def test_parse_state():
    msg = st3215.InferenceState(buses=[st3215.InferenceState_BusState(
        bus=st3215.ST3215Bus(serial_number="FOLLOWER1", port_name="/dev/tty.usb1"),  # string fields are str on encode
        motors=[
            st3215.InferenceState_MotorState(id=1, state=motor_state(2048), range_min=1024, range_max=3072),
            st3215.InferenceState_MotorState(id=2, state=motor_state(1024 | 0x8000, status=OVERLOAD_BIT), range_min=0, range_max=4095),
        ],
    )])
    buses = parse_state(msg.encode())
    bus = buses["FOLLOWER1"]
    assert bus.port == "/dev/tty.usb1"
    assert bus.motors[1].norm == 0.5, bus.motors[1]
    assert bus.motors[1].torque and not bus.motors[1].overloaded
    assert bus.motors[2].raw == 3072, bus.motors[2]  # sign bit folded the way norma-core does
    assert bus.motors[2].overloaded


def test_norm_to_raw_clamps():
    assert norm_to_raw(0.5, 1000, 3000) == 2000
    assert norm_to_raw(-1, 1000, 3000) == 1000 + SAFETY_MARGIN
    assert norm_to_raw(2, 1000, 3000) == 3000 - SAFETY_MARGIN


def test_sync_write_roundtrip():
    cmd = sync_write("FOLLOWER1", REG_GOAL, {1: (2000).to_bytes(2, "little"), 8: (1500).to_bytes(2, "little")})
    inner = st3215.CommandReader(memoryview(bytes(cmd.body)))
    serial = inner.get_target_bus_serial()
    assert (serial.decode() if isinstance(serial, (bytes, memoryview)) else serial) == "FOLLOWER1", serial
    sw = inner.get_sync_write()
    assert sw.get_address() == REG_GOAL
    got = {m.get_motor_id(): int.from_bytes(bytes(m.get_value()), "little") for m in sw.get_motors()}
    assert got == {1: 2000, 8: 1500}, got


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
