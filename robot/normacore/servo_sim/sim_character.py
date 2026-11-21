"""Play every character x gesture on the simulated ElRobot (servo_sim model) and report
peak torque (overload risk), how far each joint lags its goal (can the servo keep up?)
and the gesture's duration. Run: ../.venv/bin/python sim_character.py  (or any python with mujoco)."""
import sys, math, pathlib
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent))
import mujoco
import servo_sim as S
from character import PERSONALITIES, GESTURES, JOINTS, plan, idle_plan

m = S.build(0.010, 0.055)                         # real 55 g servos
qa, da = S.jidx(m)
lo = [m.jnt_range[m.joint(n).id][0] for n in S.JN]; hi = [m.jnt_range[m.joint(n).id][1] for n in S.JN]
to_rad = lambda i, v: lo[i] + v * (hi[i] - lo[i])
neutral = {j: (S.REACH[i] - lo[i]) / (hi[i] - lo[i]) for i, j in enumerate(JOINTS)}
KP, KD = 1 / (40 * S.TICK), 0.05

def simulate(steps, wait_arrival=True):
    d = mujoco.MjData(m)
    for i, a in enumerate(qa): d.qpos[a] = S.REACH[i]
    mujoco.mj_forward(m, d)
    sv = [S.Servo(S.REACH[i], KP, KD) for i in range(8)]
    for _ in range(int(0.5 / S.DT)):
        for i in range(8):
            tau, _ = sv[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
        mujoco.mj_step(m, d)
    t, k, shift, peak, lag = 0.0, 0, 0.0, [0.0] * 8, [0.0] * 8
    reached, active = [], {}   # per move: fraction of the way done when the next step starts
    waiting = None
    end = steps[-1].t + 4.0
    while t < end + shift:
        if waiting is not None:                   # bound flow: hold the clock until arrival
            if all(abs(d.qpos[qa[i]] - to_rad(i, v)) < math.radians(1.5) for i, v in waiting.items()) or t - wstart > 2:
                shift += t - wstart; waiting = None
        while waiting is None and k < len(steps) and t >= steps[k].t + shift:
            s = steps[k]
            for i, (g0, q0) in active.items():
                if abs(g0 - q0) > math.radians(2):
                    reached.append(min(1.0, (d.qpos[qa[i]] - q0) / (g0 - q0)))
            active = {int(j[1:]) - 1: (to_rad(int(j[1:]) - 1, v), d.qpos[qa[int(j[1:]) - 1]]) for j, v in s.goals.items()}
            for j, v in s.goals.items():
                i = int(j[1:]) - 1
                sv[i].set(to_rad(i, v), s.speed[j], s.acc[j])
            if s.wait_arrival and wait_arrival:
                waiting = {int(j[1:]) - 1: v for j, v in s.goals.items()}; wstart = t
            k += 1
        for i in range(8):
            tau, _ = sv[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
            peak[i] = max(peak[i], abs(tau) / S.STALL)
            lag[i] = max(lag[i], abs(sv[i].goal - d.qpos[qa[i]]))
        mujoco.mj_step(m, d); t += S.DT
        if k >= len(steps) and waiting is None and t > steps[-1].t + shift + 1.5: break
    return peak, reached, t

print(f"{'character':10s} {'gesture':12s} {'secs':>5s} {'shoulder%':>9s}  {'moves reached (median / worst)':>30s}")
worst = {}
allr = {}
for pn in PERSONALITIES:
    for g in GESTURES:
        peak, reached, t = simulate(plan(pn, g, neutral))
        rs = sorted(reached) or [1.0]
        print(f"{pn:10s} {g:12s} {t:5.1f} {peak[1]*100:8.0f}%  {rs[len(rs)//2]*100:12.0f}% / {rs[0]*100:4.0f}%")
        allr.setdefault(pn, []).extend(rs)
        worst[pn] = max(worst.get(pn, 0), peak[1])
    peak, _, t = simulate(idle_plan(pn, 8, neutral))
    print(f"{pn:10s} {'idle 8 s':12s} {t:5.1f} {peak[1]*100:8.0f}%")
print("\nworst shoulder torque per character:", {k: f"{v*100:.0f}%" for k, v in worst.items()})
print("median move completion per character:", {k: f"{sorted(v)[len(v)//2]*100:.0f}%" for k, v in allr.items()})
