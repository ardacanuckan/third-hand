# 03 · Lessons from the June winner

The repo https://github.com/manas-arumalla/norma-robot (MIT) says it won the "AI-Powered Robot Control" track at the June 2026 edition. The win is self-reported; we found no independent write-up. Its `claude-supervisor/` folder is the most useful prior art for our track.

## What they built

1. **Claude drives ElRobot through a custom MCP server** (`station_mcp.py`): it sees through the cameras and runs a pick-and-place (carrot into a box, back home). Their reliable hero demo.
2. **"Two brains":** a SmolVLA policy (30 teleop demos, 2.5 h training) does fast reaching at about 10 Hz; Claude watches at about 0.3 Hz, pauses the policy when it fails and finishes the grasp. Their own table marks the policy's grasp as inconsistent.
3. Two side demos: colour sorting and a yes/no gesture "oracle" with voice input.

## Parts worth reusing (credit them)

- `station_mcp.py`: tools `observe`, `get_joint_state`, `move_joints`, `set_gripper`, `save_skill`, `replay_skill`, plus policy pause/resume. Safety clamps live in the server.
- `robot_lib.py`: connect, `current_st3215()` (joints from the motor bus, never freezes), atomic sync-write moves, bus discovery.
- `grasp_model.py`: a hand-taught 3×3 grid of poses with bilinear interpolation, which gives IK without kinematics. We no longer need it for pointing (the screen points), but it is the right tool if we ever do.
- `teach_points.py` / `teach_drop.py`: record poses by moving the arm by hand.

## Their hard-won lessons

1. Start Station with `-t`.
2. Pin the follower bus serial in `station.yaml`. With leader and follower both connected, `auto` is ambiguous and the camera/joint bridge freezes. Never command the leader.
3. The camera bridge (`inference/normvla`) can freeze: drive motion from the motor bus.
4. The shoulder `j2` overloads when sent straight to a reach pose: creep in small steps (about 0.03 per 0.5 s) and tuck the elbow `j3` before lifting the shoulder. They raised `current-threshold` to 200.
5. `j8` is the jaws; `j7` is gripper rotation (their own config mixed these up).
6. Camera order flips on replug: identify by content.
7. The MCP server does not hot-reload: restart the Claude session after editing it.
8. Launch Claude Code with `--append-system-prompt`, not a full system prompt file, so it keeps its tools.
9. Bundle whole motions into one call so Claude oversees tasks instead of stepping joints.

## Why we are different

The judges have seen "Claude picks an object and drops it in a box" and the VLA supervisor idea. Our angle is a real use case: an assistant for a person soldering a real board, hands busy, voice only, with a screen that shows exactly where each part goes, camera checks on the result, and a finale where the board we built drives our soft glove. We do not train a VLA.
