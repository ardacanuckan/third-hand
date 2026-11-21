"""Third Hand arm MCP server: whole-motion tools for an LLM, each answering with what the arm actually did.

    uv run --project robot/normacore/mcp_server python robot/normacore/mcp_server/server.py          # real arm
    THIRD_HAND_FAKE=1 uv run --project robot/normacore/mcp_server python robot/normacore/mcp_server/server.py  # no hardware

Tools (one call = one whole motion; the model never sends raw joint or register values):
  arm_status, look, list_skills, give_me, go_to, gripper, perform, stop, describe_last_motion, describe_recording

Every motion is recorded from the motor bus while it runs and translated by motion_to_text, so the reply
says what happened ("gripped something at 3.1 s, jaws 35 % open"), not just what was asked.

Environment:
  THIRD_HAND_FAKE=1           simulated arm (no Station needed)
  STATION_HOST, FOLLOWER_SERIAL, LEADER_SERIAL   as for elrobot.py (.env in robot/normacore works too)
  VLA_CHECKPOINT              trained SmolVLA checkpoint folder (for give_me on the real arm)
  SMOLVLA_DIR                 norma-core/software/ai/smolvla_py (has scripts/run_policy.py), default ~/norma-core/...
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                      # robot/normacore
sys.path.insert(0, str(ROOT))

from mcp.server.fastmcp import FastMCP, Image  # noqa: E402

import motion_to_text as M  # noqa: E402

FAKE = os.environ.get("THIRD_HAND_FAKE", "") not in ("", "0", "false")
SKILLS = json.loads((HERE / "skills.json").read_text())
mcp = FastMCP("third-hand-arm", instructions=(
    "Tools for the Third Hand robot arm (ElRobot, 8 servos, jaws as gripper). To hand something to a person, "
    "use hand_over: the arm releases when it feels the person pull. Each tool runs one whole "
    "motion and reports what the arm actually did, read from its motors. Use give_me only for objects "
    "list_skills says are trained; say so plainly when something is not. After a failed or partial motion, "
    "describe what happened before retrying. Call stop if the person says stop."))

_arm = None
_lock = asyncio.Lock()
_last: M.Description | None = None
_stop = asyncio.Event()


# ----------------------------------------------------------------------------- arm access

async def arm():
    global _arm
    if _arm is None:
        if FAKE:
            from fake_arm import FakeArm
            _arm = FakeArm()
            await _arm.start()
        else:
            from elrobot import ElRobot
            _arm = await ElRobot.connect()
    return _arm


async def run_motion(name: str, coro_factory) -> str:
    """Run one motion under the lock, record it, return the result plus what the arm did."""
    global _last
    if _lock.locked():
        return "The arm is busy with another motion. Wait for it, or call stop."
    async with _lock:
        _stop.clear()
        a = await arm()
        try:
            result, d = await M.record(a, coro_factory(a))
        except Exception as e:                                   # report, never crash the server
            return f"{name} failed: {e}"
        _last = d
        return f"{name}: {result}\nWhat the arm did: {d.summary}"


# ----------------------------------------------------------------------------- tools

@mcp.tool()
async def arm_status() -> str:
    """Connection, joint positions (0..1), jaw opening, faults, and whether a motion is running."""
    try:
        a = await arm()
        bus = await a.state()
    except Exception as e:
        return f"Arm not reachable: {e}. Is Station running with --tcp, and FOLLOWER_SERIAL set?"
    joints = {f"j{m}": round(x.norm, 3) for m, x in sorted(bus.motors.items())}
    faults = [f"j{m}" for m, x in bus.motors.items() if x.overloaded]
    return json.dumps({"mode": "fake" if FAKE else "real", "follower": a.follower, "joints": joints,
                       "jaws_open": joints.get("j8"), "faults": faults or None, "busy": _lock.locked()})


@mcp.tool(structured_output=False)
async def look(camera: str = "side"):
    """One camera picture: 'side' (table camera) or 'wrist' (gripper camera). Use sparingly: the motion
    tools already report what the arm did."""
    a = await arm()
    try:
        frames = await a.frames()
    except Exception as e:
        return f"No camera frame: {e}"
    if not frames:
        return "No camera frames (fake mode has no cameras)."
    i = SKILLS.get("cameras", {}).get(camera, 0)
    return Image(data=frames[min(i, len(frames) - 1)], format="jpeg")


@mcp.tool()
async def list_skills() -> str:
    """What the arm can do: trained objects for give_me, saved poses for go_to, characters and moves for perform."""
    import character as C
    poses = sorted(json.loads((ROOT / "poses.json").read_text())) if (ROOT / "poses.json").exists() else []
    return json.dumps({"give_me (trained objects)": {k: v["task"] for k, v in SKILLS["objects"].items()},
                       "go_to (saved poses)": poses or ["home (fake mode)"] if FAKE else poses,
                       "perform characters": list(C.PERSONALITIES),
                       "perform moves": [g for g in C.GESTURES if g not in C.SCENES],
                       "perform scenes": list(C.SCENES)}, indent=1)


def _match_object(text: str):
    t = text.lower()
    for key, v in SKILLS["objects"].items():
        if any(re.search(r"\b" + re.escape(a) + r"\b", t) for a in [key] + v.get("aliases", [])):
            return key, v
    return None, None


@mcp.tool()
async def give_me(object: str, max_seconds: float = 60) -> str:
    """Fetch an object and hand it over, using the trained policy. `object` in plain words ('the glue stick').
    Only objects in list_skills are trained; anything else is refused with the list."""
    key, v = _match_object(object)
    if key is None:
        return (f"'{object}' is not a trained object. Trained: {', '.join(SKILLS['objects'])}. "
                "The policy only knows the exact objects it was trained on.")

    async def go(a):
        if FAKE:
            return await a.fake_pick(v.get("width_mm", 15))
        ckpt = os.environ.get("VLA_CHECKPOINT")
        if not ckpt:
            raise RuntimeError("VLA_CHECKPOINT is not set: no trained policy to run")
        sdir = Path(os.environ.get("SMOLVLA_DIR") or Path.home() / "norma-core/software/ai/smolvla_py").expanduser()
        ticks = int(max_seconds * SKILLS.get("policy_hz", 2))
        cmd = ["uv", "run", "python", "scripts/run_policy.py", "--checkpoint", ckpt, "--task", v["task"],
               "--bus-serial", a.follower, "--motor-ids", "1,2,3,4,5,6,7,8",
               "--max-delta-ticks", str(SKILLS.get("max_delta_ticks", 150)), "--auto", "--max-ticks", str(ticks)]
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=sdir, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.STDOUT)
        waiter = asyncio.create_task(proc.communicate())
        stopper = asyncio.create_task(_stop.wait())
        done, _ = await asyncio.wait({waiter, stopper}, timeout=max_seconds + 30, return_when=asyncio.FIRST_COMPLETED)
        if waiter not in done:
            proc.terminate(); await a.hold()
            return "stopped before the policy finished" if stopper in done else "timed out"
        stopper.cancel()
        out = (waiter.result()[0] or b"").decode(errors="replace").strip().splitlines()
        aborted = [l for l in out if "aborted" in l]
        return f"policy ran ({'safety stop: ' + aborted[-1] if aborted else 'finished'}), task '{v['task']}'"
    return await run_motion(f"give_me({key})", go)


@mcp.tool()
async def hand_over(timeout_s: float = 15) -> str:
    """Hold the object out and let go when the person pulls on it. The arm feels the pull through its
    servos (current rise and joint give, thresholds from handover_thresholds.json). Call it with the
    arm already at the handover pose holding the object (e.g. after give_me or go_to('handover'))."""
    import handover

    async def go(a):
        if FAKE:
            await a.fake_pull_after(float(os.environ.get("FAKE_PULL_AFTER", "2.0")))
        return await handover.hand_over(a, timeout=timeout_s, open_norm=SKILLS["jaws"]["open"])
    return await run_motion("hand_over", go)


@mcp.tool()
async def go_to(pose: str) -> str:
    """Move to a saved pose by name (see list_skills), e.g. 'home', 'park', 'handover'."""
    async def go(a):
        await a.go_pose(pose)
        return f"at pose '{pose}'"
    return await run_motion(f"go_to({pose})", go)


@mcp.tool()
async def gripper(action: str) -> str:
    """'open' or 'close' the jaws. Closing on an object reports whether it gripped something."""
    if action not in ("open", "close"):
        return "action must be 'open' or 'close'"

    async def go(a):
        await a.gripper(SKILLS["jaws"]["open"] if action == "open" else SKILLS["jaws"]["closed"])
        return f"jaws {action}"
    return await run_motion(f"gripper({action})", go)


@mcp.tool()
async def perform(character: str, move: str) -> str:
    """A character performs a gesture or scene (see list_skills), e.g. character='butler', move='bow'.
    Keep people and the soldering iron clear."""
    import character as C
    if character not in C.PERSONALITIES or move not in C.GESTURES:
        return f"Unknown. Characters: {', '.join(C.PERSONALITIES)}. Moves: {', '.join(C.GESTURES)}."

    async def go(a):
        if FAKE:
            await a.play_steps(C.plan(character, move, await a.joints()))
        else:
            await C.perform(a, character, move)
        return f"{character} performed {move}"
    return await run_motion(f"perform({character}, {move})", go)


@mcp.tool()
async def stop() -> str:
    """Stop now: interrupt the running motion and hold position (torque stays on)."""
    _stop.set()
    a = await arm()
    await a.hold()
    return "Stopped and holding position."


@mcp.tool()
async def describe_last_motion() -> str:
    """Step-by-step account of the last motion (times, joints, grasps), read from the motors."""
    return _last.text if _last else "No motion recorded yet."


@mcp.tool()
async def describe_recording(path: str) -> str:
    """Translate a recorded episode (Station dataset .parquet) into words: moves, grasps, faults."""
    p = Path(path).expanduser()
    if not p.exists() or p.suffix != ".parquet":
        return f"No parquet file at {p}"
    d = M.describe(M.frames_from_parquet(str(p)))
    return d.summary + "\n\n" + d.text


if __name__ == "__main__":
    mcp.run()
