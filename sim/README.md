# sim/ · 3D simulation of the demo

A browser simulation of the whole planned demo: the real ElRobot model (URDF and meshes from norma-core) posed with IK on its real joint chain and limits, a fresh SOL-MIO v1.3 from its Altium data, the parts tray, the bench screen and the soldering station.

```bash
python3 -m http.server 8000
```

Open http://localhost:8000. Views: Bench, Board, Robot, Screen. The left-hand picture shows what Claude sees (side or wrist camera).

Files:

- `index.html`: the page (three.js from jsDelivr)
- `core.js`: URDF reader, forward kinematics, damped least-squares IK, bench layout, part list
- `elrobot-model.js`: ElRobot follower URDF and meshes, packed (vertices quantized to 0.02 mm)
- `solmio-board.js`, `bench-screen.js`: board data and the bench screen renderer (same as `screen/bench-screen/`)

This is a planning and explanation tool. Do not build event features on it.
