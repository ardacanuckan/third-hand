"""Run the fine-tuned SmolVLA grasp on the ElRobot follower: one safe skill the Hub can call.

The arm must already be at the hover pose above the chosen resistor, with torque on and
Station's leader-to-follower mirroring OFF. The policy then drives all 8 joints at about
10 Hz until the jaws have closed and settled, the time runs out, or someone stops it.

Safety, on top of Station's current limits:
  - only the follower bus; it refuses the leader's serial from robot/normacore/.env
  - every goal is clamped to the servo's calibrated range minus a margin
  - a step that would move any joint more than --max-delta-ticks from where it is aborts the run
  - on any stop the arm holds where it is

    # load the checkpoint and time one prediction, no arm needed
    bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/run/final --dry-run vla/data/fake.parquet

    # on the arm, pressing Enter before every batch of moves
    bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/run/final --step

    # on the arm, continuous (what the Hub does)
    bash vla/py.sh vla/policy_grasp.py --checkpoint vla/checkpoints/run/final

Frame handling and the sync-write follow NormaCore's software/ai/smolvla_py/scripts/run_policy.py
(Apache-2.0). Differences: 8 motors, several actions per prediction, clamped goals, a stop rule.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image

from smolvla import SmolVLAPolicy
from smolvla.normalize import normalize_state, unnormalize_action
from smolvla.stats import load_stats

ROOT = Path(__file__).resolve().parents[1]
ROBOT_DIR = ROOT / "robot" / "normacore"
TASK = "pick up the resistor below the gripper"
QUEUE = "inference/normvla"
REG_GOAL = 0x2A
SAFETY_MARGIN = 20  # raw ticks kept away from each calibrated end stop (as in elrobot.py)
log = logging.getLogger("policy_grasp")


def pick_device(name: str = "auto") -> torch.device:
    if name == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(name)


def read_env() -> dict[str, str]:
    env = {}
    path = ROBOT_DIR / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return {**env, **{k: v for k, v in os.environ.items() if k in ("FOLLOWER_SERIAL", "LEADER_SERIAL", "STATION_HOST")}}


class GraspPolicy:
    """The fine-tuned policy, loaded once. predict() returns a chunk of goal_norm rows in [0, 1]."""

    def __init__(self, checkpoint: Path, device: str = "auto", task: str = TASK):
        self.device = pick_device(device)
        self.task = task
        self.stats = {k: v.to(self.device) for k, v in load_stats(Path(checkpoint) / "stats.safetensors").items()}
        self.policy = SmolVLAPolicy.from_pretrained(checkpoint, config_overrides={"load_vlm_weights": False}, strict=False).to(self.device)
        self.cuda = self.device.type == "cuda"
        if not self.cuda:
            self.policy = self.policy.float()  # bf16 backbone needs CUDA autocast; use fp32 on Mac and CPU
        self.policy.eval()
        self.image_keys = tuple(self.policy.config.image_keys) or ("observation.images.cam0", "observation.images.cam1")
        self.n_joints = int(self.policy.config.action_dim)
        self.tokens, self.mask = self.policy.tokenize_task(task, device=self.device)

    def warmup(self) -> float:
        """One prediction on a blank frame. The first one is slow (about 5 s on MPS), so do it before the demo."""
        buf = io.BytesIO()
        Image.new("RGB", (224, 224), (200, 200, 200)).save(buf, "JPEG")
        t = time.perf_counter()
        self.predict([0.5] * self.n_joints, [buf.getvalue()] * len(self.image_keys))
        return time.perf_counter() - t

    @torch.no_grad()
    def predict(self, state: list[float], jpegs: list[bytes]) -> np.ndarray:
        if len(jpegs) < len(self.image_keys):
            raise RuntimeError(f"frame has {len(jpegs)} images, the policy needs {len(self.image_keys)}")
        st = torch.tensor(state[: self.n_joints], dtype=torch.float32, device=self.device).unsqueeze(0)
        batch = {"observation.state": normalize_state(st, self.stats),
                 "observation.language.tokens": self.tokens, "observation.language.attention_mask": self.mask}
        for key, jpg in zip(self.image_keys, jpegs):
            with Image.open(io.BytesIO(jpg)) as im:
                arr = np.asarray(im.convert("RGB"), dtype=np.uint8)
            batch[key] = torch.from_numpy(arr.copy()).permute(2, 0, 1).float().unsqueeze(0).to(self.device) / 255.0
        with torch.autocast(device_type="cuda", dtype=torch.bfloat16, enabled=self.cuda):
            pred = self.policy.predict_action_chunk(batch)[0]
        chunk = unnormalize_action(pred.float(), self.stats)
        return chunk.float().cpu().clamp(0.0, 1.0).numpy()  # (chunk_size, n_joints)


@dataclass
class GraspConfig:
    bus_serial: str
    motor_ids: tuple[int, ...] = (1, 2, 3, 4, 5, 6, 7, 8)
    timeout_s: float = 8.0
    rate_hz: float = 10.0
    actions_per_inference: int = 10
    max_delta_ticks: int = 100
    jaw_index: int = 7               # j8 in the joints list
    jaw_closed_below: float = 0.45   # position_norm; ElRobot jaws are about 0.78 open, 0.22-0.34 holding
    settle_frames: int = 5           # jaws must stay closed this many frames
    min_seconds: float = 1.0
    step_mode: bool = False          # wait for Enter before every batch of moves


def goal_raw(norm: float, rmin: int, rmax: int) -> int:
    lo, hi = rmin + SAFETY_MARGIN, rmax - SAFETY_MARGIN
    return int(max(lo, min(hi, round(rmin + norm * (rmax - rmin)))))


async def fetch_frame(client, last_id: bytes = b"", timeout: float = 3.0):
    """Newest normvla frame whose id differs from last_id (the queue updates at about 10 Hz)."""
    from target.gen_python.protobuf.drivers.inferences import normvla
    while True:
        qr = client.read_from_tail(QUEUE, offset=b"\x00", limit=1, step=1, buf_size=1)
        entry = await asyncio.wait_for(qr.data.get(), timeout=timeout)
        if entry is None:
            raise RuntimeError(f"{QUEUE} closed without a frame ({qr.err})")
        frame = normvla.FrameReader(memoryview(bytes(entry.Data)))
        fid = bytes(frame.get_global_frame_id())
        if fid != last_id:
            return frame, fid
        await asyncio.sleep(0.02)


async def policy_grasp(client, gp: GraspPolicy, cfg: GraspConfig, stop: asyncio.Event | None = None) -> dict:
    """Run the grasp from the hover pose. Returns {ok, reason, steps, inferences, seconds, jaw}."""
    from elrobot import sync_write  # vendored station_py, protobufs and our sync-write helper
    from station_py import send_commands

    env = read_env()
    if env.get("LEADER_SERIAL") and cfg.bus_serial == env["LEADER_SERIAL"]:
        raise RuntimeError("refusing to command the leader arm")
    t0, steps, inferences, closed_for, last_id = time.monotonic(), 0, 0, 0, b""
    reason, jaw = "timeout", float("nan")

    async def hold(frame) -> None:
        cur = {mid: int(j.get_position()).to_bytes(2, "little") for mid, j in zip(cfg.motor_ids, frame.get_joints())}
        await send_commands(client, [sync_write(cfg.bus_serial, REG_GOAL, cur)])

    frame, last_id = await fetch_frame(client, last_id)
    while True:
        joints = frame.get_joints()
        state = [j.get_position_norm() for j in joints]
        chunk = gp.predict(state, [bytes(im.get_jpeg()) for im in frame.get_images()])
        inferences += 1
        if cfg.step_mode:
            preview = " ".join(f"{v:.2f}" for v in chunk[0])
            await asyncio.get_running_loop().run_in_executor(None, input, f"next goals [{preview}]  Enter = move, Ctrl-C = stop ")
        for action in chunk[: cfg.actions_per_inference]:
            if stop is not None and stop.is_set():
                reason = "stopped"
                await hold(frame)
                return _result(False, reason, steps, inferences, t0, jaw)
            joints = frame.get_joints()
            raws = [goal_raw(float(a), int(j.get_range_min()), int(j.get_range_max())) for a, j in zip(action, joints)]
            delta = max(abs(r - int(j.get_position())) for r, j in zip(raws, joints))
            if cfg.max_delta_ticks and delta > cfg.max_delta_ticks:
                await hold(frame)
                return _result(False, f"aborted: a joint would jump {delta} ticks (limit {cfg.max_delta_ticks})", steps, inferences, t0, jaw)
            await send_commands(client, [sync_write(cfg.bus_serial, REG_GOAL, {m: r.to_bytes(2, "little") for m, r in zip(cfg.motor_ids, raws)})])
            steps += 1
            await asyncio.sleep(1.0 / cfg.rate_hz)
            frame, last_id = await fetch_frame(client, last_id)
            jaw = frame.get_joints()[cfg.jaw_index].get_position_norm()
            closed_for = closed_for + 1 if jaw < cfg.jaw_closed_below else 0
            elapsed = time.monotonic() - t0
            if closed_for >= cfg.settle_frames and elapsed >= cfg.min_seconds:
                await hold(frame)
                return _result(True, "jaws closed", steps, inferences, t0, jaw)
            if elapsed > cfg.timeout_s:
                await hold(frame)
                return _result(False, reason, steps, inferences, t0, jaw)


def _result(ok: bool, reason: str, steps: int, inferences: int, t0: float, jaw: float) -> dict:
    return {"ok": ok, "reason": reason, "steps": steps, "inferences": inferences,
            "seconds": round(time.monotonic() - t0, 2), "jaw": round(float(jaw), 3)}


def dry_run(gp: GraspPolicy, parquet: Path | None, n: int) -> None:
    """Predict on recorded frames (or a blank one) and report the timing. Sends nothing."""
    if parquet:
        import pyarrow.parquet as pq
        t = pq.read_table(parquet, columns=["joints", "images"])
        rows = [(r["joints"], r["images"]) for r in t.slice(0, min(n, t.num_rows)).to_pylist()]
        samples = [([j["position_norm"] for j in js], [im["jpeg"] for im in ims]) for js, ims in rows]
    else:
        buf = io.BytesIO()
        Image.new("RGB", (224, 224), (200, 200, 200)).save(buf, "JPEG")
        samples = [([0.5] * gp.n_joints, [buf.getvalue()] * len(gp.image_keys))] * n
    print(f"device {gp.device}, joints {gp.n_joints}, cameras {list(gp.image_keys)}, task {gp.task!r}")
    for i, (state, jpegs) in enumerate(samples):
        t = time.perf_counter()
        chunk = gp.predict(state, jpegs)
        ms = (time.perf_counter() - t) * 1000
        print(f"frame {i}: {ms:6.0f} ms  chunk {tuple(chunk.shape)}  first goal {np.round(chunk[0], 3).tolist()}")


async def main_async(a: argparse.Namespace) -> None:
    gp = GraspPolicy(a.checkpoint, a.device, a.task)
    if a.dry_run is not None:
        dry_run(gp, a.dry_run if str(a.dry_run) else None, a.frames)
        return
    env = read_env()
    bus = a.bus_serial or env.get("FOLLOWER_SERIAL")
    if not bus:
        raise SystemExit("no follower serial: pass --bus-serial or set FOLLOWER_SERIAL in robot/normacore/.env")
    print(f"warming up the policy on {gp.device} ... {gp.warmup():.1f} s")
    sys.path.insert(0, str(ROBOT_DIR))
    import elrobot  # noqa: F401  (sets up the vendored station_py and protobuf paths)
    from station_py import new_station_client
    cfg = GraspConfig(bus_serial=bus, motor_ids=tuple(int(x) for x in a.motor_ids.split(",")), timeout_s=a.timeout,
                      rate_hz=a.rate, actions_per_inference=a.actions_per_inference, max_delta_ticks=a.max_delta_ticks,
                      jaw_closed_below=a.jaw_closed_below, step_mode=a.step)
    print(f"follower {bus} on {a.server or env.get('STATION_HOST', 'localhost')}, motors {cfg.motor_ids}, "
          f"max delta {cfg.max_delta_ticks} ticks, timeout {cfg.timeout_s} s. Mirroring must be OFF.")
    client = await new_station_client(a.server or env.get("STATION_HOST", "localhost"), log)
    result = await policy_grasp(client, gp, cfg)
    print(json.dumps(result))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--task", default=TASK)
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    p.add_argument("--dry-run", type=Path, nargs="?", const=Path(""), default=None,
                   help="no arm: predict on frames from this parquet (or a blank frame) and time it")
    p.add_argument("--frames", type=int, default=3, help="frames to predict in --dry-run")
    p.add_argument("--server", default=None, help="Station host (default STATION_HOST from .env, else localhost)")
    p.add_argument("--bus-serial", default=None, help="follower serial (default FOLLOWER_SERIAL from .env)")
    p.add_argument("--motor-ids", default="1,2,3,4,5,6,7,8")
    p.add_argument("--timeout", type=float, default=8.0)
    p.add_argument("--rate", type=float, default=10.0)
    p.add_argument("--actions-per-inference", type=int, default=10)
    p.add_argument("--max-delta-ticks", type=int, default=100)
    p.add_argument("--jaw-closed-below", type=float, default=0.45)
    p.add_argument("--step", action="store_true", help="press Enter before every batch of moves")
    a = p.parse_args()
    logging.basicConfig(level=logging.WARNING)
    sys.path.insert(0, str(ROBOT_DIR))
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        print("\nstopped by hand. The arm holds its last goal; use elrobot hold() or the e-stop if needed.")


if __name__ == "__main__":
    main()
