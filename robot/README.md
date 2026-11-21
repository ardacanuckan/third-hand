# robot/ · ARM workstream

Owner: ARM. Turns the ElRobot into a library that implements [`contracts/robot.py`](../contracts/robot.py).

Deliverables A1–A6 are in [docs/05-team-plan.md](../docs/05-team-plan.md). Read [docs/02](../docs/02-normacore-station.md) and [docs/03](../docs/03-june-winner-lessons.md) first.

Suggested layout:

```
robot/
  fake_robot.py      A1  same interface, no hardware, can be told to miss a grip
  robot_lib.py       A2  Station connection, motor-bus reads, sync-write moves (port from the June winner, credit them)
  station.yaml       A2  follower bus pinned, cameras as JPEG, current-threshold 200
  teach.py           A3  torque off, move by hand, save named poses
  poses.json         A3  taught poses, committed after every teaching session
  skills.py          A4  fetch_cup, place_handover, go_inspect, park, home
  reliability.py     A5  50-cycle harness and report
```
