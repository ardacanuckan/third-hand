# mcp_server: the arm as LLM tools

One MCP tool call = one whole motion. While it runs, the server records the motor bus and answers
with what the arm actually did (`motion_to_text`): "gripped something at 0.9 s (jaws 36 % open,
450 mA), carried it, let go". The LLM never sends joint angles or servo registers.

| Tool | Does |
|---|---|
| `arm_status` | joints, jaw opening, faults, busy |
| `list_skills` | trained objects, saved poses, characters, moves, scenes |
| `give_me(object)` | runs the trained SmolVLA policy for a trained object (`skills.json`); refuses anything else |
| `hand_over(timeout_s)` | hold the object out, release when the person pulls (servo current + joint give; `handover.py --calibrate` first) |
| `go_to(pose)` | a saved pose from `poses.json` (teach with `examples/07_poses.py`) |
| `gripper(open/close)` | jaws; closing reports whether something was gripped |
| `perform(character, move)` | one of the 10 characters × 24 gestures/scenes |
| `stop` | interrupt and hold |
| `look(side/wrist)` | one camera picture (use sparingly) |
| `describe_last_motion` | step-by-step account of the last motion |
| `describe_recording(path)` | translate a Station episode `.parquet` into words |

## Run

```bash
cd robot/normacore/mcp_server && uv sync
THIRD_HAND_FAKE=1 uv run python test_client.py      # no hardware: starts the server and calls every tool
```

Claude Code: copy `mcp.json` into `.mcp.json` at the repo root (or merge it into the BRAIN server's
config) and restart Claude Code. Set `THIRD_HAND_FAKE` to `"1"` to try it without the arm.

On the arm: Station running with `--tcp`, `FOLLOWER_SERIAL` in `robot/normacore/.env`, and for
`give_me` a trained checkpoint:

```bash
export VLA_CHECKPOINT=~/Downloads/smolvla-nebius/checkpoints/<run-tag>/final
export SMOLVLA_DIR=~/norma-core/software/ai/smolvla_py      # patched with vla_train/*.patch
python3 robot/normacore/vla_train/prepare_arm.py --slow 0.5  # safe speed/acc first
```

## Adding an object

Train the policy on it first, then add it to `skills.json` with the exact training task text and
some aliases. `give_me` only accepts objects listed there.

## Safety

- One motion at a time (a lock); `stop` interrupts `give_me` and holds position.
- `give_me` runs `run_policy.py` with `--max-delta-ticks 150` (any bigger jump is refused).
- `ElRobot.connect` refuses the leader bus. Keep a hand on the power switch for the first runs.
