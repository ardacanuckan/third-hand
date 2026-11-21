# vla_train: train a SmolVLA policy for the ElRobot

A learned policy drives the arm in a closed loop, about 10 times a second: camera images + joints in,
joint goals out, no Claude/MCP picture-by-picture step in between. It is NormaCore's own trainer,
`norma-core/software/ai/smolvla_py` (SmolVLA, base `lerobot/smolvla_base`), which reads Station's
parquet episodes directly. Out of the box it assumes the 6-motor SO-101; `smolvla-elrobot-8-joints.patch`
makes it take the joint count from the data (ElRobot: 8) and adds `--device` for CPU smoke tests.

## 1. Check the episodes

```bash
python check_episodes.py episodes/*.parquet --frames frames/
```

Look at `frames/`: the task text must name what the arm actually picks up. To fix a label (originals stay):

```bash
python relabel_episodes.py --task "give me the blue glue stick" --slug blue-glue-stick --out relabeled/ episodes/ep-*.parquet
```

The 21 Nov episodes 4-7 were saved as "give me the red LED" but show a blue glue stick; they are
relabelled to "give me the blue glue stick" (and `tasks.json` gets a glue stick entry).

## 2. Get the trainer and patch it

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/norma-core/norma-core.git
cd norma-core && git sparse-checkout set software/ai/smolvla_py
git apply /path/to/third-hand/robot/normacore/vla_train/smolvla-elrobot-8-joints.patch
cd software/ai/smolvla_py && uv sync
```

Tested against norma-core commit 6b494f7 (10 Nov 2026).

## 3. Train (needs an NVIDIA GPU)

```bash
uv run python scripts/train.py --parquets /path/to/episodes/*.parquet \
    --steps 20000 --batch-size 64 --output checkpoints/elrobot-glue-stick
```

No GPU at hand: `./scripts/build_bundle.sh /path/to/episodes/*.parquet` makes `smolvla-bundle.zip`
(after applying the patch) and `nebius.md` in the trainer folder walks through a cloud run. A smoke
test without a GPU: `--device cpu --steps 2 --batch-size 1 --num-workers 0`.

## 4. Run it on the arm

```bash
python3 robot/normacore/vla_train/prepare_arm.py --slow 0.5     # safe speed/acc on every servo, torque on
uv run python scripts/run_policy.py --checkpoint checkpoints/elrobot-glue-stick/final \
    --task "give me the blue glue stick" --bus-serial <FOLLOWER_SERIAL> \
    --motor-ids 1,2,3,4,5,6,7,8 --max-delta-ticks 150           # SPACE = one step; add --auto later
```

- `--task` must be exactly the training text. `--bus-serial` is the follower, never the leader.
- `run_policy.py` only writes goal positions, so speed and acceleration are whatever the servos had;
  `prepare_arm.py` sets the tested `JOINT_PROFILE` first (shoulder and elbow gentle).
- `--max-delta-ticks` stops any step that jumps more than that (150 ticks ~ 13 deg). Start stepping
  with SPACE, a hand on the power switch, before trying `--auto`.
- Inference without a GPU runs on CPU (slow, a few seconds per step on a laptop).
