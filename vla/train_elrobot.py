"""Fine-tune SmolVLA on ElRobot grasp demos (8 joints, table and wrist cameras).

Based on NormaCore's software/ai/smolvla_py/scripts/train.py (Apache-2.0, Norma Core
contributors; model code by the Hugging Face team). Changes for ElRobot:

- The state and action size come from the dataset (8 for ElRobot: j1..j7 plus the jaws).
  The upstream script fixes them at 6 (SO-101), which would drop j7 and the jaws.
- It runs on CUDA, Apple MPS or CPU. MPS and CPU are only for smoke tests.
- bf16 autocast, TF32 and fused AdamW are used only on CUDA.
- train_info.json is written next to the checkpoints (joints, cameras, task, episodes).

Local smoke test (after `bash vla/setup.sh`):
    bash vla/py.sh vla/train_elrobot.py --parquets vla/data/fake.parquet --steps 3 \
        --batch-size 2 --device cpu --output vla/checkpoints/smoke

On Nebius this file is shipped in the bundle by vla/nebius/submit.sh.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from functools import partial
from pathlib import Path

import torch
from torch.utils.data import DataLoader

from smolvla import SmolVLAPolicy
from smolvla.dataset import PickAndPlaceDataset, collate_samples
from smolvla.normalize import normalize_action, normalize_state
from smolvla.stats import compute_stats, save_stats

IMAGE_KEYS = ("observation.images.cam0", "observation.images.cam1")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--parquets", type=Path, nargs="+", required=True, help="Dataset parquet files (merged).")
    p.add_argument("--output", type=Path, default=Path("vla/checkpoints/run"))
    p.add_argument("--steps", type=int, default=10000)
    p.add_argument("--batch-size", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--weight-decay", type=float, default=1e-10)
    p.add_argument("--warmup-steps", type=int, default=1000)
    p.add_argument("--decay-steps", type=int, default=30000)
    p.add_argument("--decay-lr", type=float, default=2.5e-6)
    p.add_argument("--grad-clip", type=float, default=10.0)
    p.add_argument("--save-every", type=int, default=2000)
    p.add_argument("--log-every", type=int, default=20)
    p.add_argument("--num-workers", type=int, default=2)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--base-checkpoint", default="lerobot/smolvla_base")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    return p.parse_args()


def pick_device(name: str) -> torch.device:
    if name == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(name)


def lr_lambda(step: int, nominal_warmup: int, nominal_decay: int, total_steps: int, decay_lr: float, peak_lr: float) -> float:
    # Upstream schedule: linear warmup, cosine decay; both shrink proportionally on short runs.
    if total_steps < nominal_decay:
        scale = total_steps / nominal_decay
        warmup = max(int(nominal_warmup * scale), 1)
        decay = total_steps
    else:
        warmup = max(nominal_warmup, 1)
        decay = nominal_decay
    if step < warmup:
        return (step + 1) / warmup
    s = min(step - warmup, decay - warmup)
    cos = 0.5 * (1 + math.cos(math.pi * s / max(decay - warmup, 1)))
    alpha = decay_lr / peak_lr
    return (1 - alpha) * cos + alpha


def build_batch(raw: dict, policy, stats, device) -> dict:
    batch = {k: (v.to(device, non_blocking=True) if isinstance(v, torch.Tensor) else v) for k, v in raw.items()}
    batch["observation.state"] = normalize_state(batch["observation.state"], stats)
    batch["action"] = normalize_action(batch["action"], stats)
    tokens, mask = policy.tokenize_task(batch.pop("task"), device=device)
    batch["observation.language.tokens"] = tokens
    batch["observation.language.attention_mask"] = mask
    return batch


def save_checkpoint(policy, out: Path, stats_path: Path, info: dict) -> None:
    policy.save_pretrained(out)
    (out / "stats.safetensors").write_bytes(stats_path.read_bytes())
    (out / "train_info.json").write_text(json.dumps(info, indent=2))


def main() -> None:
    args = parse_args()
    torch.manual_seed(args.seed)
    device = pick_device(args.device)
    cuda = device.type == "cuda"
    use_bf16 = cuda and torch.cuda.is_bf16_supported()
    if cuda:
        torch.set_float32_matmul_precision("high")
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
        print(f"GPU: {torch.cuda.get_device_name(0)} | bf16 autocast: {'on' if use_bf16 else 'off'}")
    else:
        print(f"device: {device} (smoke test only, real training needs a CUDA GPU)")

    args.output.mkdir(parents=True, exist_ok=True)
    ds = PickAndPlaceDataset(args.parquets, image_keys=IMAGE_KEYS)
    n_joints = ds.n_joints
    tasks = sorted(set(ds._tasks_all))
    print(f"episodes: {ds.total_episodes}  frames: {len(ds)}  joints: {n_joints}  tasks: {tasks}")
    if n_joints != 8:
        print(f"WARNING: expected 8 joints for ElRobot (j1..j7 + jaws), got {n_joints}")

    stats = compute_stats(ds._state, ds._action)
    stats_path = args.output / "stats.safetensors"
    save_stats(stats, stats_path)
    stats = {k: v.to(device) for k, v in stats.items()}

    print(f"loading base checkpoint {args.base_checkpoint} ...")
    policy = SmolVLAPolicy.from_pretrained(
        args.base_checkpoint,
        config_overrides={
            "image_keys": list(IMAGE_KEYS),
            "state_dim": n_joints,
            "action_dim": n_joints,
            "load_vlm_weights": False,
            "empty_cameras": 0,
        },
        strict=False,
    ).to(device)
    if not cuda:
        # the SmolVLM backbone loads in bf16 and relies on CUDA autocast; elsewhere run everything in fp32
        policy = policy.float()
    policy.train()
    trainable = [p for p in policy.parameters() if p.requires_grad]
    print(f"trainable params: {sum(p.numel() for p in trainable):,} / {sum(p.numel() for p in policy.parameters()):,}")

    opt = torch.optim.AdamW(trainable, lr=args.lr, betas=(0.9, 0.95), weight_decay=args.weight_decay, fused=cuda)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lr_lambda=partial(
        lr_lambda, nominal_warmup=args.warmup_steps, nominal_decay=args.decay_steps,
        total_steps=args.steps, decay_lr=args.decay_lr, peak_lr=args.lr))
    loader = DataLoader(
        ds, batch_size=args.batch_size, shuffle=True, num_workers=args.num_workers,
        collate_fn=partial(collate_samples, image_keys=IMAGE_KEYS), pin_memory=cuda,
        drop_last=len(ds) >= args.batch_size, persistent_workers=args.num_workers > 0,
    )
    info = {"base": args.base_checkpoint, "joints": n_joints, "image_keys": list(IMAGE_KEYS), "tasks": tasks,
            "episodes": ds.total_episodes, "frames": len(ds), "parquets": [str(p) for p in args.parquets],
            "batch_size": args.batch_size, "steps": args.steps}

    step, t0, run_loss, run_n = 0, time.time(), 0.0, 0
    while step < args.steps:
        for raw in loader:
            if step >= args.steps:
                break
            batch = build_batch(raw, policy, stats, device)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=use_bf16):
                loss, out = policy.forward(batch)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(trainable, args.grad_clip)
            opt.step()
            sched.step()
            run_loss += out["loss"]
            run_n += 1
            if (step + 1) % args.log_every == 0 or step + 1 == args.steps:
                dt = time.time() - t0
                print(f"step {step + 1:>6}/{args.steps}  loss {run_loss / run_n:.4f}  lr {sched.get_last_lr()[0]:.2e}  ({(step + 1) / max(dt, 1e-9):.2f} step/s)", flush=True)
                run_loss, run_n = 0.0, 0
            if (step + 1) % args.save_every == 0:
                save_checkpoint(policy, args.output / f"step-{step + 1:06d}", stats_path, {**info, "step": step + 1})
            step += 1

    final = args.output / "final"
    save_checkpoint(policy, final, stats_path, {**info, "step": step})
    print(f"done: final checkpoint at {final}")


if __name__ == "__main__":
    main()
