# Notice

## Prepared before the event

Created before the hackathon opened on 21 November 2026 at 11:00 Berlin time, as research and planning:

- `docs/`: research notes and plans
- `sim/`: 3D simulation of the planned demo
- `screen/bench-screen/`: bench screen prototype
- `contracts/`: draft interfaces
- `board/solmio-v1.3.json`: data exported from our own SOL-MIO board design

Say this in the submission and follow the event's rules on pre-existing work.

## Third-party material

- **ElRobot URDF and meshes** in `sim/elrobot-model.js` are derived from `hardware/elrobot/simulation` in https://github.com/norma-core/norma-core, © NormaCore, licensed under the Apache License 2.0. A copy of the license is in `sim/third_party/ElRobot-LICENSE-Apache-2.0.txt`. Changes: the STL meshes were re-encoded (indexed, int16-quantized at 0.02 mm) and packed with the URDF into one JavaScript file.
- **norma-core v0.1.0-beta.10** in `robot/normacore/vendor/` (the `station_py` client, the gremlin protobuf runtime and code generator, the `.proto` files, two upstream examples, and Python stubs generated from those `.proto` files), © NormaCore, MIT License (`robot/normacore/vendor/LICENSE`). The Station binary itself is downloaded by `install_station.sh` and not stored in this repo.
- **three.js** is loaded at runtime from jsDelivr (MIT).
- Ideas and any code we port from https://github.com/manas-arumalla/norma-robot (MIT, © NormaCore) and https://github.com/norma-core/norma-core (MIT) must keep their license notices; credit them in the README and the pitch.
