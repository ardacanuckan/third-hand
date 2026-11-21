# robot/normacore · connect to and control the ElRobot

Default files for talking to NormaCore's ElRobot through Station v0.1.0-beta.10 (the latest release):

| File | What |
|---|---|
| `install_station.sh` | Downloads the Station binary for this machine into `bin/` (Apple Silicon Mac or Linux) |
| `run_station.sh` | Starts Station: web UI on http://localhost:8889, Python API on port 8888 |
| `station.yaml` | Default Station config: servo current limit 200 mA, cameras at 448 px, joints + camera bridge |
| `.env.example` | Leader and follower bus serials; copy to `.env` |
| `elrobot.py` | Our control library: connect, read joints, move safely, gripper, torque, cameras, named poses |
| `examples/` | Seven small scripts, from "is Station running" to teaching poses |
| `test_offline.py` | Checks message decoding and encoding without a robot |
| `vendor/` | norma-core v0.1.0-beta.10 Python client (`station_py`), protobuf runtime and generated stubs (MIT) |

Tested so far: the offline tests pass, Station v0.1.0-beta.10 starts with `station.yaml`, and `elrobot.py` connects to it. **Not yet tested with the arm attached.**

## First connection (about 15 minutes)

```bash
bash robot/normacore/install_station.sh
```

```bash
bash robot/normacore/run_station.sh
```

1. Plug in both arms (follower 12 V, leader 7.4 V) and both cameras, ideally through a powered USB hub.
2. Open http://localhost:8889. Each arm is a bus named by its controller serial, with 8 servos.
3. Calibrate in the web UI: move every joint of each arm by hand through its full range, then click **Auto Calibrate** on the follower. Clear the workspace and keep a hand on the power switch.
4. Identify the buses:

```bash
python3 robot/normacore/examples/01_list_buses.py
```

5. Copy `.env.example` to `.env` and fill in `FOLLOWER_SERIAL` and `LEADER_SERIAL`. Copy `station.yaml` to `station.local.yaml` and put the follower serial in `st3215-bus`, then restart Station.
6. Check that reading and moving work:

```bash
python3 robot/normacore/examples/02_read_joints.py
```

```bash
python3 robot/normacore/examples/03_nudge_joint.py j1 0.05
```

## Examples

| Script | Does |
|---|---|
| `00_check_install.py` | Python side OK, Station binary present, ports listening. No robot needed. |
| `01_list_buses.py` | Every bus with servo ids, positions, calibration, torque, overload |
| `02_read_joints.py [s]` | Live j1..j8 for a few seconds |
| `03_nudge_joint.py j1 0.05` | Moves one joint a little and back, after you confirm |
| `04_gripper.py open/close/0.5` | Jaws (j8) |
| `05_camera_snapshot.py` | Saves the latest frame from each camera to `snapshots/` |
| `06_torque.py off/on` | Torque off to move the arm by hand, on to hold |
| `07_poses.py save/go/list NAME` | Teach and replay named poses in `poses.json` (commit it) |

## Using the library

```python
import asyncio
from elrobot import ElRobot

async def main():
    async with await ElRobot.connect() as arm:
        print(await arm.joints())          # {"j1": 0.51, ..., "j8": 0.78}
        await arm.move({"j3": 0.40})       # tuck the elbow first
        await arm.move({"j2": 0.35})       # then the shoulder
        await arm.gripper(0.78)            # open the jaws
        jpegs = await arm.frames()         # one JPEG per camera
        await arm.save_pose("home")

asyncio.run(main())
```

Safety built in:

- It refuses to command the leader bus, and asks for `FOLLOWER_SERIAL` when more than one bus is connected.
- Targets are clamped to each servo's calibrated range minus a 20-tick margin.
- Moves go in small steps at low speed and acceleration, and stop with an error on a servo overload.
- Joint state comes from the motor bus, which keeps working when the camera bridge freezes.

## Troubleshooting

- **No buses:** is the follower powered (12 V)? Use a data USB cable, not a charge-only one. On Linux, add yourself to `dialout`.
- **No camera frames:** on macOS, give the terminal that runs Station camera access (System Settings → Privacy & Security → Camera). Quit Photo Booth, Zoom or Chrome if they hold the camera. Pin `st3215-bus` to the follower serial.
- **Overload error:** power-cycle the follower, then move back to home in small steps with the elbow tucked first.
- **Wrong arm moves:** check `.env`; the follower is the 12 V arm with the camera on the wrist.
