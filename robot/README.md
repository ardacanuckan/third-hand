# robot/ · ARM workstream

Owner: ARM. Turns the ElRobot into a library that implements [`contracts/robot.py`](../contracts/robot.py).

**Start here: [`normacore/`](normacore)** has everything to connect to and control the arm today: the Station installer, a default config, `elrobot.py` and seven examples.

Deliverables A1–A6 are in [docs/05-team-plan.md](../docs/05-team-plan.md). Read [docs/02](../docs/02-normacore-station.md) and [docs/03](../docs/03-june-winner-lessons.md) first.

Suggested next files:

```
robot/
  normacore/         connect, read, move, gripper, cameras, poses (done; extend here)
  fake_robot.py      A1  same interface as contracts/robot.py, no hardware, can be told to miss a grip
  real_robot.py      A2  implements contracts/robot.py on top of normacore/elrobot.py
  skills.py          A4  fetch_cup, place_handover, go_inspect, park, home
  reliability.py     A5  50-cycle harness and report
```

Taught poses live in `normacore/poses.json` (`examples/07_poses.py`).
