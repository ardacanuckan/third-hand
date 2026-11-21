# vla/ · The fine-tuned SmolVLA grasp

The grasp inside `pick(slot)`:
- The Hub brings the arm to the hover pose above the chosen resistor.
- A SmolVLA policy, fine-tuned on our own leader-arm demos, closes in and grips.
- The Hub lifts and hands over.

We use NormaCore's own trainer, [`software/ai/smolvla_py`](https://github.com/norma-core/norma-core/tree/main/software/ai/smolvla_py) (base model `lerobot/smolvla_base` from Hugging Face), and their Station dataset tools.

**Status (Sat 21 Nov evening).**

Tested without the arm:
- a fake dataset in Station's format passes the checker;
- training runs on CPU with all 8 joints;
- the Nebius bundle unpacks and trains locally exactly as the job will;
- the checkpoint loads and predicts: about 0.5 s per prediction on Apple MPS, 0.9 s on CPU;
- the control loop passes 5 tests against a fake Station.

Not yet tested: the real arm, a real Nebius GPU run.

## One-time setup

```bash
bash vla/setup.sh
```

```bash
bash robot/normacore/install_station.sh
```

The first installs NormaCore's trainer and the base model into `vla/.norma-core` (git-ignored, about 3 GB). The second provides Station plus `dataset-generator` and `dataset-mp4`. For Nebius see [nebius/README.md](nebius/README.md).

## 1. Record demos (ROBOT and VLA, about an hour for 60)

Station runs with both arms connected and mirroring on, so the leader drives the follower.

1. In the Station web UI (`:8889`), press **Tag**: this is the start tag.
2. For each episode, about 10 s:
   - start with the arm still at the hover pose above a resistor, jaws open;
   - go down, close the jaws on the resistor, lift about 5 cm, hold still.
3. Between episodes, take at least 8 s: put the resistor back, return to hover, and change to another slot now and then.
4. After the last episode, press **Tag** again: this is the end tag. In **History**, note the frame numbers of both tags.

Rules that matter more than the count:
- **Same motion every time:** same speed, same approach. Throw away a fumbled episode rather than keeping it.
- **Vary only what should vary:** the slot, small offsets, which resistor.
- **Keep the scene fixed:** rack, light and cameras must not move between recording and the stage. Never replug a camera, because Station can swap `cam0` and `cam1`.
- **Start where the Hub starts:** the hover pose here must be the one the Hub uses (ROBOT's R3).

## 2. Export and check

```bash
bash vla/export.sh <start_frame> <end_frame> resistor
```

This writes `vla/data/resistor.parquet` and runs the checker, which prints one line per episode: frames, seconds, joints, cameras, and what the jaws did. It also saves the first and last frame of every episode to `vla/data/peek-resistor/` and renders a preview video. Fix anything marked `NO` before training.

## 3. Train on Nebius

```bash
bash vla/nebius/submit.sh vla/data/resistor.parquet
```

```bash
bash vla/nebius/fetch.sh <RUN_TAG> final
```

`submit.sh` bundles NormaCore's package with our `train_elrobot.py` and the data, uploads it, and starts the job: about 10k steps, batch 64, an L40S, a checkpoint every 2,000 steps. `fetch.sh` with only the tag lists the saved checkpoints; with `final` or `step-006000` it downloads one.

## 4. Try it on the arm

These steps need someone at the power switch. Mirroring must be **off**, and the arm must be at the hover pose above a resistor.

```bash
bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/<RUN_TAG>/final --dry-run
```

```bash
bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/<RUN_TAG>/final --step
```

```bash
bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/<RUN_TAG>/final
```

1. `--dry-run` sends nothing: it loads the checkpoint and times the predictions. Add a parquet path after `--dry-run` to predict on recorded frames.
2. `--step` waits for Enter before every batch of moves.
3. With neither flag it runs continuously. It stops when the jaws have closed and settled, after 8 s, or on a safety abort, and prints `{"ok": ..., "reason": ...}`.

The follower serial and Station host come from `robot/normacore/.env`.

## How the Hub calls it

```python
from policy_grasp import GraspPolicy, GraspConfig, policy_grasp

gp = GraspPolicy("vla/checkpoints/<RUN_TAG>/final")   # load once at Hub start
gp.warmup()                                            # the first prediction takes about 5 s
result = await policy_grasp(client, gp, GraspConfig(bus_serial=FOLLOWER_SERIAL))
if not result["ok"]:
    ...                                                # fall back to the scripted grasp
```

## Safety

On top of Station's per-servo current limit:
- It refuses the leader's serial.
- Every goal is clamped to the servo's calibrated range minus 20 ticks.
- A move that would jump any joint more than `--max-delta-ticks` (default 100) aborts the run.
- On any stop the arm holds where it is.

The policy only ever starts from the hover pose, inside `pick`. There is no free joint control for the model.

## What we changed from NormaCore's scripts

| Upstream (`smolvla_py`) | Here | Why |
|---|---|---|
| `train.py` fixes state and action at 6 (SO-101) | `train_elrobot.py` takes the size from the data (8) | Otherwise j7 and the jaws would be dropped |
| `train.py` needs CUDA | CUDA, MPS or CPU; on MPS and CPU the model runs in fp32 | Smoke tests on the laptop |
| `run_policy.py`: motors 1–6, one action per prediction | `policy_grasp.py`: motors 1–8, 10 actions per prediction, clamped goals, a stop rule, a Hub API | A real-time grasp that ends by itself |

## Files

| File | What |
|---|---|
| `setup.sh`, `py.sh` | Install NormaCore's trainer; run a script in its environment |
| `export.sh` | Recorded frames to `vla/data/<name>.parquet`, check, preview |
| `check_dataset.py` | One line per episode, flags bad ones |
| `make_fake_dataset.py` | A synthetic dataset in the same format, for tests |
| `train_elrobot.py` | The trainer (local smoke test or on Nebius) |
| `policy_grasp.py` | The grasp skill and its CLI |
| `test_policy_grasp.py` | Control-loop tests against a fake Station |
| `nebius/` | One-time setup, `submit.sh`, `fetch.sh` |
