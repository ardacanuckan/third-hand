# 02 · NormaCore Station and ElRobot

Findings from reading `norma-core/norma-core` (main and dev branches), the ElRobot hardware docs, and a hackathon starter repo that uses Station.

## Station in one paragraph

Station is a single binary that owns the servos and cameras, records everything into its storage (NormFS), and serves a web UI and a TCP API. There is **no official MCP server and no high-level motion API**: you read and write servo registers. Cartesian moves and IK are on us; we avoid them with taught poses.

```bash
./station --web --tcp          # web UI on :8889, NormFS API on :8888
```

`-t` / `--tcp` is required for the Python API. Config is `station.yaml` next to the binary.

## Python client

- Package `station_py` in `software/station/shared/station_py`. Protobuf stubs are generated into `target/gen_python`; the starter repo's `install.sh` downloads Station v0.1.0-beta.10 and builds them.
- Connect: `client = await new_station_client("localhost", logger)`.
- Subscribe: `client.follow("st3215/inference", queue)` gives every bus and every motor's full register dump.
- Command: build `st3215.Command(target_bus_serial=..., write=... | sync_write=...)`, wrap it in `commands.DriverCommand(type=STC_ST3215_COMMAND, body=cmd.encode())`, then `await send_commands(client, [cmd])`.

## ST3215 registers we use

| Register | Address | Notes |
|---|---|---|
| Torque enable | `0x28` | 0 = limp (for teaching by hand), 1 = hold |
| Acceleration | `0x29` | write before the goal |
| Goal position | `0x2A` | 2 bytes, little endian, raw ticks |
| Goal speed | `0x2E` | write before the goal |
| Present position | `0x38` | 2 bytes, sign bit `0x8000` |
| Status | `0x41` | `0x20` = overload fault |

Each motor's calibrated `range_min`/`range_max` comes with its state; map 0..1 to that range. Send speed and acceleration first, then all goals in one `sync_write` so the joints move together.

## Cameras

- UVC cameras are opened by Station itself (on macOS the camera permission belongs to the terminal that started it). Do not open them again with OpenCV.
- Frames arrive on queue `usbvideo/<md5 of the camera's unique id>` as `RxEnvelope` → `FramesPack`.
- On the dev branch the default storage codec is **VP8**; set `codec: jpeg` under `usb-video` to get JPEG frames directly.
- Frames are resized so the short side is **224 px** by default (`resize_target`). Raise it for joint inspection.
- `inference/normvla` delivers joints and images together, but it can freeze (see doc 03). Read joints from `st3215/inference`.

## ElRobot

- 7 joints + jaws, 8 ST3215 servos (12 V followers, 7.4 V leaders), about 430 mm reach, about 800 g, fully 3D printed.
- Joints `j1`..`j8` = motor ids 1..8. `j7` rotates the gripper; **`j8` opens and closes the jaws** (open about 0.78, gripping about 0.22–0.34 in `position_norm`).
- Two cameras: one on the wrist (the jaws are visible in its frame), one on the table. Camera order can swap on replug: identify them by what they see.
- URDF and meshes: `hardware/elrobot/simulation/`. Browser playground: https://normacore.dev/elrobot-urdf/ (sliders only, no API).
- Station has a simulation mode only for the Yahboom dog driver, not for the arm. There is no physics simulator for ElRobot.

## What our simulation showed (sim/)

With the real URDF chain and limits, a damped least-squares IK reached every target on our bench with under 1 mm error: five cup slots (above and grip), the handover zone, the SOL-MIO power corner at 16–45 mm above the board, and an inspection pose 50 mm up. Pointing straight down fails when the tool is high above the table (wrist joint `j6` hits its limit near 1.76 rad), so approach poses use a tilted tool axis.

## Sources

- https://github.com/norma-core/norma-core (MIT; ElRobot hardware Apache-2.0)
- Starter repo using Station: https://github.com/svaichu/robot-pizza-cup
- https://normacore.dev/opensource/station/
- https://nebius.com/customer-stories/normacore
