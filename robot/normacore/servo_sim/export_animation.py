"""Simulate every character x gesture (+ idle) from an upright standing pose and save the joint
motion the servos actually produce (not the plan) at 30 fps for the viewer.

    ../.venv/bin/python export_animation.py viewer/anim.json
"""
import json, math, pathlib, sys
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import mujoco
import servo_sim as S
from character import GESTURES, JOINTS, PERSONALITIES, _settings, idle_plan, plan

STAND = [0.0, 0.1, -1.4, 0.9, 0.0, 0.9, 0.0, 0.3]     # upright "desk lamp" pose, rad
FPS = 30
m = S.build(0.010, 0.055)                              # real 55 g servos
qa, da = S.jidx(m)
lo = [m.jnt_range[m.joint(n).id][0] for n in S.JN]
hi = [m.jnt_range[m.joint(n).id][1] for n in S.JN]
to_rad = lambda i, v: lo[i] + v * (hi[i] - lo[i])
neutral = {j: (STAND[i] - lo[i]) / (hi[i] - lo[i]) for i, j in enumerate(JOINTS)}
KP, KD = 1 / (40 * S.TICK), 0.05


def simulate(steps):
    d = mujoco.MjData(m)
    for i, a in enumerate(qa): d.qpos[a] = STAND[i]
    mujoco.mj_forward(m, d)
    sv = [S.Servo(STAND[i], KP, KD) for i in range(8)]
    for _ in range(int(0.5 / S.DT)):
        for i in range(8):
            tau, _ = sv[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
        mujoco.mj_step(m, d)
    frames, torque, peak = [], [], 0.0
    t, k, shift, waiting, wstart = 0.0, 0, 0.0, None, 0.0
    every = int(round(1 / (FPS * S.DT)))
    n = 0
    while True:
        if waiting is not None:
            if all(abs(d.qpos[qa[i]] - to_rad(i, v)) < math.radians(1.5) for i, v in waiting.items()) or t - wstart > 2:
                shift += t - wstart; waiting = None
        while waiting is None and k < len(steps) and t >= steps[k].t + shift:
            s = steps[k]
            for j, v in s.goals.items():
                i = int(j[1:]) - 1
                sv[i].set(to_rad(i, v), s.speed[j], s.acc[j])
            if s.wait_arrival:
                waiting = {int(j[1:]) - 1: v for j, v in s.goals.items()}; wstart = t
            k += 1
        tq = 0.0
        for i in range(8):
            tau, _ = sv[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
            if i == 1: tq = abs(tau) / S.STALL
        peak = max(peak, tq)
        if n % every == 0:
            frames.append([round(float(d.qpos[a]), 4) for a in qa])
            torque.append(round(tq * 100))
        mujoco.mj_step(m, d); t += S.DT; n += 1
        moving = max(abs(d.qvel[x]) for x in da)
        if k >= len(steps) and waiting is None and t > steps[-1].t + shift + 0.6 and moving < 0.02:
            break
        if t > 30: break
    for _ in range(int(0.4 * FPS)):          # short still tail so loops breathe
        frames.append(frames[-1]); torque.append(torque[-1])
    return frames, torque, peak


out = {"fps": FPS, "joints": S.JN, "stand": STAND, "characters": {}, "clips": {}}
for name, p in PERSONALITIES.items():
    acc, speed = _settings(p, JOINTS)
    out["characters"][name] = dict(archetype=p.archetype, laban=p.laban, acc=acc, speed=speed,
                                   size=p.size, tempo=p.tempo, blend=p.blend, anticipation=p.anticipation,
                                   overshoot=p.overshoot, tremor=p.tremor, smooth=p.smooth,
                                   breath=p.breath, breath_s=p.breath_s, glance_s=p.glance_s)
    for g in list(GESTURES) + ["idle"]:
        steps = idle_plan(p, 8, neutral) if g == "idle" else plan(p, g, neutral)
        frames, torque, peak = simulate(steps)
        out["clips"][f"{name}/{g}"] = dict(q=frames, torque=torque, peak=round(peak * 100))
        print(f"{name:10s} {g:12s} {len(frames) / FPS:5.1f}s shoulder peak {peak * 100:3.0f}%", file=sys.stderr)

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else HERE / "viewer" / "anim.json")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(out, separators=(",", ":")))
print("wrote", path, round(path.stat().st_size / 1e6, 2), "MB", file=sys.stderr)
