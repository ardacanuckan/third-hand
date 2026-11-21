"""Simulate teleoperated ElRobot episodes (MuJoCo + STS3215 servo model) with ground truth, in the
NormaCore Station dataset layout (joints only: no camera images).

    python generate.py --episodes 3000 --out out/ [--workers 8] [--seed 1]

A simulated operator (leader arm) drives the follower through scripted scenarios: clean handovers,
missed grasps and retries, objects that tip or slip, wrong object, two parts, obstacle detours,
hesitation, regrasps, tiny parts, shoulder overload, emergency stop, dropped frames, jaws starting
closed, character performances and idle. Grasping is simulated at the jaws: an object between them
blocks closing, so the servo stalls and draws current, like the real recordings.

Writes out/episodes-NNN.parquet (Station columns; images empty) and out/truth.jsonl (what really
happened per episode: events with times, success, a reference narrative).
"""
from __future__ import annotations

import argparse, json, math, pathlib, random, sys, time
import multiprocessing as mp

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "servo_sim")); sys.path.insert(0, str(HERE.parent))

TICK = 2 * math.pi / 4096
STALL, W0 = 2.94, 4.71
STALL_MA = 2700.0
STAND = [0.0, 0.1, -1.4, 0.9, 0.0, 0.9, 0.0, 0.3]
DT = 0.001
LEADER_DT = 0.01
REC_DT = 0.1
JAW_GAP0_MM, JAW_MM_PER_RAD = 50.2, 23.0          # inner finger gap at j8 = 0 and closing per radian
J8_MAX = 2.2028
HANDOVER = np.array([0.135, 0.15, 0.07])

OBJECTS = {   # name: (task text, width between the jaws mm, height on the table mm)
    "glue stick":     ("give me the blue glue stick", 18.0, 18.0),
    "red LED":        ("give me the red LED", 5.0, 9.0),
    "green LED":      ("give me the green LED", 5.0, 9.0),
    "resistor":       ("give me a resistor", 2.5, 2.5),
    "red jumper wire": ("give me the red jumper wire", 2.6, 2.6),
    "USB cable":      ("give me the USB cable", 11.0, 11.0),
    "Arduino":        ("give me the Arduino", 1.6, 18.0),
}
TINY = {"resistor", "red jumper wire", "Arduino"}

SCENARIOS = {  # name: (episodes per 3000, difficulty 1-3)
    "clean": (400, 1), "handover_pull": (400, 2), "miss_retry": (250, 2), "tip_over": (150, 3), "slip": (200, 3),
    "wrong_object": (150, 2), "two_parts": (150, 2), "obstacle": (150, 2), "hesitation": (150, 2),
    "regrasp": (100, 3), "tiny_part": (250, 3), "overload": (100, 3), "estop": (100, 2),
    "frame_drops": (150, 3), "jaws_closed_start": (100, 1), "character": (150, 1), "idle": (50, 1),
}


def j8_from_norm(n):  # jaw norm: 1 = open, 0 = shut (the real arm's calibration)
    return (1 - n) * J8_MAX


def gap_mm(q8):
    return JAW_GAP0_MM - JAW_MM_PER_RAD * q8


def q8_for_gap(w):
    return (JAW_GAP0_MM - w) / JAW_MM_PER_RAD


# ----------------------------------------------------------------------------- world

class World:
    def __init__(self):
        import mujoco, servo_sim as S
        self.mj, self.S = mujoco, S
        self.m = S.build(0.010, 0.055)
        self.m.opt.timestep = DT
        self.d = mujoco.MjData(self.m)
        self.qa, self.da = S.jidx(self.m)
        self.lo = [self.m.jnt_range[self.m.joint(n).id][0] for n in S.JN]
        self.hi = [self.m.jnt_range[self.m.joint(n).id][1] for n in S.JN]
        self.b_base, self.b_j1, self.b_j2 = (self.m.body(n).id for n in ("Gripper_Base_v1_1", "Gripper_Jaw_01_v1_1", "Gripper_Jaw_02_v1_1"))
        self.kd = mujoco.MjData(self.m)

    def mouth(self, d=None):
        d = d or self.d
        return 0.5 * (d.xipos[self.b_j1] + d.xipos[self.b_j2])

    def tool_dir(self, d):
        v = self.mouth(d) - d.xipos[self.b_base]
        return v / np.linalg.norm(v)

    def ik(self, target, seed, down=True, iters=80):
        """Joint angles that put the mouth at target, jaws pointing down. Returns (q, error_m)."""
        d, mj = self.kd, self.mj
        q = np.array(seed, float)
        idx = [0, 1, 2, 3, 5]
        want_dir = np.array([0, 0, -1.0])

        def res(qv):
            for i, a in enumerate(self.qa): d.qpos[a] = qv[i]
            mj.mj_kinematics(self.m, d)
            r = self.mouth(d) - target
            return np.concatenate([r, 0.04 * (self.tool_dir(d) - want_dir)]) if down else r
        for _ in range(iters):
            r = res(q)
            if np.linalg.norm(r[:3]) < 0.002 and (not down or np.linalg.norm(r[3:]) < 0.004):
                break
            J = np.zeros((len(r), len(idx)))
            for k, i in enumerate(idx):
                qq = q.copy(); qq[i] += 1e-4
                J[:, k] = (res(qq) - r) / 1e-4
            dq = -J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(len(r)), r)
            for k, i in enumerate(idx):
                q[i] = np.clip(q[i] + np.clip(dq[k], -0.2, 0.2), self.lo[i] + 0.05, self.hi[i] - 0.05)
        return q, float(np.linalg.norm(res(q)[:3]))


# ----------------------------------------------------------------------------- operator plan

class Plan:
    """Leader keyframes: (duration, goal (8 rad, None = unchanged), label). Jaw-only frames too."""

    def __init__(self, world, rng, speed):
        self.w, self.rng, self.speed = world, rng, speed
        self.keys: list[tuple[float, list, str]] = []
        self.q = list(STAND)

    def _dur(self, q):
        dist = max(abs(a - b) for a, b in zip(q[:7], self.q[:7]))
        return (0.5 + 1.1 * dist) / self.speed * self.rng.uniform(0.85, 1.2)

    def arm(self, q, label, dur=None):
        q = [float(x) for x in q[:7]] + [self.q[7]]
        self.keys.append((dur or self._dur(q), q, label)); self.q = q

    def jaw(self, q8, label, dur=None):
        q = self.q[:7] + [float(np.clip(q8, 0.0, J8_MAX))]
        self.keys.append((dur or (0.35 + 0.5 * abs(q[7] - self.q[7])) / self.speed, q, label)); self.q = q

    def wait(self, s, label="pause"):
        self.keys.append((s, list(self.q), label))

    def at(self, xyz, label, z_up=0.0, dur=None, offset=(0, 0), down=True):
        tgt = np.array([xyz[0] + offset[0], xyz[1] + offset[1], xyz[2] + z_up])
        q, err = self.w.ik(tgt, self.q, down=down)
        if err > 0.012:
            raise ValueError(f"unreachable {label} {tgt.round(3)} err {err:.3f}")
        self.arm(list(q[:7]), label, dur)

    def open(self, label="open jaws"):
        self.jaw(j8_from_norm(self.rng.uniform(0.55, 0.65)), label)

    def squeeze(self, width, label="close on object"):
        self.jaw(q8_for_gap(width) + self.rng.uniform(0.05, 0.14), label, dur=self.rng.uniform(0.4, 0.8) / self.speed)
        self.wait(self.rng.uniform(0.4, 0.9), "waits for the grip")     # the follower's jaws lag the leader's
        self.jaw(q8_for_gap(width) + self.rng.uniform(-0.01, 0.01), "relax grip", dur=self.rng.uniform(0.3, 0.6))

    def home(self):
        self.arm(STAND[:7], "back to standing")


def grasp_z(obj):
    return max(obj["h"] / 2000, 0.004) + 0.004


def pick(p: Plan, obj, miss=None):
    """Approach, (miss), close. Returns nothing; the world decides whether it got the object."""
    off = miss or (0, 0)
    p.at(obj["pos"], f"above the {obj['name']}", z_up=0.06 + p.rng.uniform(0, 0.03), offset=off)
    if p.rng.random() < 0.3:
        p.at(obj["pos"], "corrects aim", z_up=0.03, offset=(off[0] + p.rng.uniform(-0.01, 0.01), off[1]))
    p.at(obj["pos"], f"down to the {obj['name']}", z_up=grasp_z(obj) - obj["pos"][2], offset=off)
    p.wait(p.rng.uniform(0.1, 0.6), "aims")
    p.squeeze(obj["w"])


def carry_and_hand(p: Plan, obj, high=False, dest=None, wait_s=None, keep=False):
    dest = HANDOVER + np.array([p.rng.uniform(-0.02, 0.02), p.rng.uniform(-0.02, 0.02), p.rng.uniform(-0.01, 0.05)]) if dest is None else dest
    p.at(obj["pos"], "lift", z_up=(0.12 if high else 0.07) + p.rng.uniform(0, 0.02))
    if high:
        mid = (np.array(obj["pos"]) + dest) / 2
        p.at(mid, "over the obstacle", z_up=0.17 + p.rng.uniform(0, 0.03), down=False)
    p.at(dest, "over the handover zone", z_up=0.04)
    p.at(dest, "lower to the hand", z_up=0.0)
    p.wait(wait_s or p.rng.uniform(0.2, 1.0), "waits for the hand")
    if keep:                                        # nobody took it: keep holding, back off
        p.at(dest, "gives up, keeps holding", z_up=0.06)
        return dest
    p.open("release")
    p.at(dest, "retreat", z_up=0.06)
    return dest


# ----------------------------------------------------------------------------- simulation

def simulate(world, plan: Plan, objects, scen, rng, extra):
    import mujoco
    S, m, d = world.S, world.m, world.d
    mujoco.mj_resetData(m, d)
    q0 = list(STAND)
    q0[7] = j8_from_norm(rng.uniform(0.3, 0.62))           # jaws start part-open, like the real recordings
    if extra.get("jaws_closed"):
        q0[7] = j8_from_norm(0.03)
    for i, a in enumerate(world.qa): d.qpos[a] = q0[i]
    mujoco.mj_forward(m, d)
    kp, kd = 1 / (40 * TICK), 0.05
    sv = [S.Servo(q0[i], kp, kd) for i in range(8)]
    for s in sv: s.set(s.goal, 1500, 60)                       # teleop mirroring: fast but ramped
    # leader trajectory: min-jerk between keyframes + tremor
    T_end = sum(k[0] for k in plan.keys) + 1.0
    if extra.get("idle"):
        T_end = rng.uniform(15, 25)
    key_t, acc = [], 0.0
    for dur, q, lab in plan.keys:
        key_t.append((acc, acc + dur, q, lab)); acc += dur
    trem_f = [rng.uniform(3, 7) for _ in range(8)]; trem_a = [rng.uniform(0.0, 0.006) * extra.get("tremor", 1.0) for _ in range(7)] + [0.0]
    held, events, truth_t = None, [], {}
    rec, t, next_rec, k_leader = [], 0.0, 0.0, 0
    leader = list(q0)
    prev = list(q0)
    fault_t, estop_t = extra.get("fault_t"), extra.get("estop_t")
    slip_t = extra.get("slip_t"); tip = extra.get("tip")
    tip_release_t = None
    leader_goal_rec = list(q0)
    pull = extra.get("pull")
    wait_key = next((i for i, k in enumerate(key_t) if k[3] == "waits for the hand"), None) if pull else None
    det, det_fired, pull_t0, touch_t0 = None, None, None, None
    if pull and wait_key is not None:
        from handover import PullDetector
        w0 = key_t[wait_key][0]
        pull_t0 = w0 + 0.6 + pull["after"] if pull["kind"] != "nobody" else None
        touch_t0 = w0 + 0.6 + pull["after"] * 0.4 if pull["kind"] == "touch_then_pull" else None
        pdir = np.array(pull["dir"]) / np.linalg.norm(pull["dir"])
        span = {f"j{i + 1}": (0, (world.hi[i] - world.lo[i]) / TICK) for i in range(8)}
    while t < T_end:
        # leader goal at 100 Hz
        if k_leader % int(LEADER_DT / DT) == 0:
            cur = None
            for i_k, (a, b, q, lab) in enumerate(key_t):
                if a <= t < b:
                    x = (t - a) / max(1e-6, b - a); f = x * x * x * (10 - 15 * x + 6 * x * x)
                    start = key_t[i_k - 1][2] if i_k else q0
                    cur = [s_ + (e - s_) * f for s_, e in zip(start, q)]
                    break
            if cur is None:
                cur = list(key_t[-1][2]) if key_t else list(q0)
            leader = [c + trem_a[j] * math.sin(2 * math.pi * trem_f[j] * t + j) for j, c in enumerate(cur)]
            if estop_t is not None and t >= estop_t:
                leader = list(leader_goal_rec)                    # leader frozen where it was
            else:
                leader_goal_rec = list(leader)
            for j in range(8):
                sv[j].goal = leader[j]
                sv[j].set(leader[j])
        # world: grasp, slip, tip, release (every 10 ms)
        if k_leader % 10 == 0:
            mouth = world.mouth()
            q8 = d.qpos[world.qa[7]]
            if held is None:
                for o in objects:
                    if o["state"] != "table":
                        continue
                    near = np.linalg.norm(mouth[:2] - o["pos"][:2]) < 0.012 and abs(mouth[2] - (o["pos"][2] + grasp_z(o) - o["pos"][2])) < 0.012
                    if near and gap_mm(q8) <= o["w"] + 0.8:
                        held = o; o["state"] = "held"
                        events.append({"t": round(t, 2), "type": "grasp", "object": o["name"]})
                        if tip and not tip.get("done"):
                            tip["done"] = True; tip_release_t = t + rng.uniform(0.2, 0.45)
                        break
            else:
                held["pos"] = mouth.copy()
                if tip_release_t is not None and t >= tip_release_t:
                    held["state"] = "table"; held["pos"] = np.array(tip["to"])
                    events.append({"t": round(t, 2), "type": "tipped_out", "object": held["name"]}); held = None; tip_release_t = None
                elif slip_t is not None and t >= slip_t:
                    held["state"] = "dropped"; held["pos"] = np.array([mouth[0], mouth[1], held["h"] / 2000])
                    events.append({"t": round(t, 2), "type": "slip", "object": held["name"]}); held = None; slip_t = None
                elif gap_mm(q8) > held["w"] + 4.0:
                    where = "handover" if np.linalg.norm(mouth[:2] - HANDOVER[:2]) < 0.06 else "table"
                    held["state"] = "handed" if where == "handover" else "table"
                    held["pos"] = np.array([mouth[0], mouth[1], held["h"] / 2000])
                    events.append({"t": round(t, 2), "type": "release", "object": held["name"], "where": where}); held = None
        # the person: a brief touch and/or a pull on the held object (force on the gripper)
        if pull and wait_key is not None:
            d.xfrc_applied[world.b_base, :3] = 0.0
            if touch_t0 is not None and touch_t0 <= t < touch_t0 + pull["touch_dur"] and held is not None:
                d.xfrc_applied[world.b_base, :3] = pull["touch_force"] * pdir
                if not truth_t.get("touch"):
                    truth_t["touch"] = True; events.append({"t": round(t, 2), "type": "touch", "force_n": round(pull["touch_force"], 1)})
            if pull_t0 is not None and t >= pull_t0 and held is not None:
                f = pull["force"] * min(1.0, (t - pull_t0) / pull["ramp"])
                d.xfrc_applied[world.b_base, :3] = f * pdir
                if not truth_t.get("pull"):
                    truth_t["pull"] = True; events.append({"t": round(t, 2), "type": "pull_start", "force_n": round(pull["force"], 1)})
            # the arm's own detector, live at 50 Hz, only while it waits at the handover pose
            a, b = key_t[wait_key][0], key_t[wait_key][1]
            if det_fired is None and a + 0.3 <= t < b and k_leader % 20 == 0 and held is not None:
                if det is None:
                    det = PullDetector({"baseline_s": 0.25})
                qn = {f"j{i + 1}": (d.qpos[world.qa[i]] - world.lo[i]) / (world.hi[i] - world.lo[i]) for i in range(8)}
                cn = {f"j{i + 1}": abs(getattr(sv[i], "tau", 0.0)) / STALL * STALL_MA for i in range(8)}
                ev = det.update(t, qn, cn, span)
                if ev:
                    det_fired = t
                    events.append({"t": round(t, 2), "type": "pull_detected", "joint": ev["joint"],
                                   "current_rise_ma": ev["current_ma"], "deflection_deg": ev["deflection_deg"],
                                   "latency_s": round(t - pull_t0, 2) if pull_t0 and t >= pull_t0 else None})
                    shift = t - b                                   # end the wait now, run the rest earlier
                    key_t = [k if i <= wait_key - 1 else ((k[0] + shift if i > wait_key else k[0]), k[1] + shift, k[2], k[3])
                             for i, k in enumerate(key_t)]
                    T_end += shift
        # servos + contact
        for j in range(8):
            tau, duty = sv[j].step(d.qpos[world.qa[j]], d.qvel[world.da[j]])
            if fault_t is not None and t >= fault_t and j == extra.get("fault_joint", 1):
                tau = 0.0
            sv[j].tau = tau
            d.qfrc_applied[world.da[j]] = tau
        if held is not None:
            qb = q8_for_gap(held["w"])
            pen = d.qpos[world.qa[7]] - qb
            if pen > 0:
                d.qfrc_applied[world.da[7]] += -200.0 * pen - 1.5 * d.qvel[world.da[7]]   # stiff object: jaws stall at its width
        mujoco.mj_step(m, d)
        t += DT; k_leader += 1
        if fault_t is not None and t >= fault_t and not truth_t.get("fault"):
            truth_t["fault"] = True; events.append({"t": round(t, 2), "type": "overload", "joint": f"j{extra.get('fault_joint', 1) + 1}"})
        if estop_t is not None and t >= estop_t and not truth_t.get("estop"):
            truth_t["estop"] = True; events.append({"t": round(t, 2), "type": "estop"})
        if t >= next_rec:
            q = [float(d.qpos[a]) for a in world.qa]
            qd = [float(d.qvel[a]) for a in world.da]
            cur_ma = [abs(sv[j].tau) / STALL * STALL_MA + rng.uniform(0, 3) for j in range(8)]
            rec.append((t, q, list(leader), cur_ma, qd))
            next_rec += REC_DT + rng.uniform(0, 0.015)
    return rec, events, T_end


# ----------------------------------------------------------------------------- scenarios

def place_objects(rng, names):
    out = []
    for n in names:
        task, w, h = OBJECTS[n]
        for _ in range(50):
            r, a = rng.uniform(0.14, 0.23), math.radians(rng.uniform(-50, 50))
            p = np.array([r * math.sin(a), r * math.cos(a), h / 2000])
            if all(np.linalg.norm(p[:2] - o["pos"][:2]) > 0.06 for o in out) and np.linalg.norm(p[:2] - HANDOVER[:2]) > 0.07:
                break
        out.append({"name": n, "task": task, "w": w, "h": h, "pos": p, "start": p.copy(), "state": "table"})
    return out


def build(world, scen, rng):
    speed = rng.uniform(0.6, 1.5)
    extra = {}
    if scen == "hesitation":
        speed *= 0.7; extra["tremor"] = 2.5
    p = Plan(world, rng, speed)
    normal = [n for n in OBJECTS if n not in TINY]
    if scen == "tiny_part":
        names = [rng.choice(sorted(TINY))]
    elif scen in ("wrong_object", "two_parts"):
        names = rng.sample(normal, 2)
    else:
        names = [rng.choice(normal)]
    objs = place_objects(rng, names)
    target = objs[-1] if scen == "wrong_object" else objs[0]
    notes = []
    if scen == "idle":
        extra["idle"] = True
        return p, objs, target, extra, ["The arm stays in its standing pose; nobody moves the leader."]
    if scen == "character":
        return None, [], None, {"character": True}, []
    if scen == "jaws_closed_start":
        extra["jaws_closed"] = True; p.q[7] = j8_from_norm(0.03)
        notes.append("The jaws start closed and are opened first.")
    if rng.random() < 0.15 and scen != "jaws_closed_start":
        p.wait(rng.uniform(0.5, 2.0), "waits before starting")
    p.open()
    if scen == "miss_retry":
        pick(p, target, miss=(rng.choice([-1, 1]) * rng.uniform(0.02, 0.035), rng.uniform(-0.02, 0.02)))
        p.open("opens again after missing")
        p.at(target["pos"], "re-aims", z_up=0.06)
        pick(p, target)
        notes.append(f"The first grasp misses the {target['name']}; the operator re-aims and grasps it.")
    elif scen == "tip_over":
        landed = dict(target)
        landed["pos"] = np.array(target["pos"]) + np.array([rng.uniform(-0.02, 0.02), rng.uniform(0.015, 0.028), 0])
        extra["tip"] = {"to": landed["pos"].tolist()}
        pick(p, target)
        p.wait(0.5, "notices"); p.open("opens again"); p.at(target["pos"], "backs off", z_up=0.06)
        p.wait(rng.uniform(0.5, 1.5), "looks for it")
        pick(p, landed)
        notes.append(f"The {target['name']} tips out of the jaws on the first grasp; the operator finds it and grasps it again.")
        carry_and_hand(p, landed)
        p.home()
        return p, objs, target, extra, notes
    elif scen == "wrong_object":
        wrong = objs[0]
        pick(p, wrong)
        p.at(wrong["pos"], "lifts the wrong one", z_up=0.04)
        p.at(wrong["pos"], "puts it back", z_up=grasp_z(wrong) - wrong["pos"][2])
        p.open("lets go of the wrong object")
        p.at(wrong["pos"], "backs off", z_up=0.06)
        pick(p, target)
        notes.append(f"The operator first grasps the {wrong['name']}, puts it back, then takes the {target['name']}.")
    else:
        pick(p, target)
    if scen == "regrasp":
        p.at(target["pos"], "lift a little", z_up=0.05)
        p.jaw(q8_for_gap(target["w"]) - rng.uniform(0.08, 0.12), "loosens the grip")
        p.wait(rng.uniform(0.3, 0.8), "adjusts")
        p.squeeze(target["w"], "squeezes again")
        notes.append("The grip is loosened and re-tightened during the carry; the object stays in the jaws.")
    if scen == "slip":
        notes.append(f"The {target['name']} slips out of the jaws during the carry.")
    if scen == "overload":
        notes.append("The shoulder servo (j2) overloads during the carry and switches off; the arm sags.")
    if scen == "estop":
        notes.append("The emergency stop is pressed: the arm freezes where it is.")
    if scen == "handover_pull":
        kind = rng.choices(["pull", "touch_then_pull", "nobody"], [0.55, 0.2, 0.25])[0]
        extra["pull"] = {"kind": kind, "after": rng.uniform(0.8, 3.0), "force": rng.uniform(3.0, 10.0),
                         "ramp": rng.uniform(0.15, 0.5), "touch_force": rng.uniform(1.5, 3.5),
                         "touch_dur": rng.uniform(0.05, 0.14),
                         "dir": [rng.uniform(0.2, 1.0), rng.uniform(0.2, 1.0), rng.uniform(-0.2, 0.6)]}
        carry_and_hand(p, target, wait_s=8.0, keep=(kind == "nobody"))
        notes.append({"pull": "The arm holds the object out and waits; the person grabs it and pulls; the arm feels the pull and opens the jaws.",
                      "touch_then_pull": "The person brushes the object first (no release), then grabs and pulls; the arm opens the jaws on the pull.",
                      "nobody": "The arm holds the object out, nobody takes it, and after 8 s it keeps holding and goes back."}[kind])
    else:
        carry_and_hand(p, target, high=(scen == "obstacle"))
    if scen == "obstacle":
        notes.append("The arm lifts high over an obstacle on the way to the handover zone.")
    if scen == "hesitation":
        notes.append("The operator hesitates: slow moves, pauses and a shaky hand.")
    if scen == "two_parts":
        second = objs[1]
        p.at(second["pos"], "goes for the second part", z_up=0.07)
        pick(p, second)
        carry_and_hand(p, second)
        notes.append(f"Two parts are handed over: the {target['name']}, then the {second['name']}.")
    p.home()
    return p, objs, target, extra, notes


def run_character(world, rng):
    """A character performance from character.py on the servo model (no objects)."""
    import character as C
    names, moves = list(C.PERSONALITIES), list(C.GESTURES)
    name, move = rng.choice(names), rng.choice(moves)
    neutral = {j: (STAND[i] - world.lo[i]) / (world.hi[i] - world.lo[i]) for i, j in enumerate(C.JOINTS)}
    steps = C.plan(name, move, neutral)
    p = Plan(world, rng, 1.0)
    t_prev, cur = 0.0, list(STAND)
    for s in steps:
        q = list(cur)
        for j, v in s.goals.items():
            i = int(j[1:]) - 1
            q[i] = world.lo[i] + v * (world.hi[i] - world.lo[i])
        p.keys.append((max(0.05, s.t - t_prev), q, "character step")); t_prev = s.t; cur = q
    p.keys.append((1.0, list(cur), "settle"))
    return p, name, move


# ----------------------------------------------------------------------------- truth + records

def narrative(scen, target, events, notes, success, extra):
    if scen == "idle":
        return notes[0]
    if scen == "character":
        return f"The arm performs '{extra['move']}' as the {extra['name']} character. No object is handled."
    bits = []
    for e in events:
        if e["type"] == "grasp": bits.append(f"grips the {e['object']} at {e['t']:.1f} s")
        elif e["type"] == "release": bits.append(f"releases it {'into the waiting hand' if e['where'] == 'handover' else 'on the table'} at {e['t']:.1f} s")
        elif e["type"] == "slip": bits.append(f"the {e['object']} slips out at {e['t']:.1f} s")
        elif e["type"] == "tipped_out": bits.append(f"the {e['object']} tips out of the jaws at {e['t']:.1f} s")
        elif e["type"] == "overload": bits.append(f"servo {e['joint']} overloads and switches off at {e['t']:.1f} s")
        elif e["type"] == "estop": bits.append(f"emergency stop at {e['t']:.1f} s")
        elif e["type"] == "touch": bits.append(f"the person brushes the object at {e['t']:.1f} s ({e['force_n']} N, too brief to count as a pull)")
        elif e["type"] == "pull_start": bits.append(f"the person grabs it and pulls ({e['force_n']} N) at {e['t']:.1f} s")
        elif e["type"] == "pull_detected": bits.append(f"the arm feels the pull at {e['t']:.1f} s ({e['joint']}: +{e['current_rise_ma']} mA, {e['deflection_deg']} deg give)")
    head = f"Task: {target['task']}. " if target else ""
    story = ("The arm " + ", then ".join(bits) + ".") if bits else "The arm never gets hold of anything."
    extra_notes = " ".join(n for n in notes if not n.isupper())
    return f"{head}{story} {extra_notes} Outcome: {'success' if success else 'not delivered'}.".replace("  ", " ")


def to_rows(ep_id, rec, rng, drop_frames):
    """Station dataset rows: per-episode calibration ranges, ticks + norms, current, velocity."""
    import character as C
    lo, hi = WORLD.lo, WORLD.hi
    ranges = []
    for i in range(8):
        half = (hi[i] - lo[i]) / 2 / TICK
        c = 2048 + rng.randint(-120, 120)
        ranges.append((int(max(0, c - half)), int(min(4095, c + half))))

    def norm(i, q):
        n = (q - lo[i]) / (hi[i] - lo[i])
        return 1 - n if i == 7 else n                      # jaws: 1 = open, as on the real arm
    rows, t0 = [], 1_795_000_000_000_000_000 + ep_id * 60_000_000_000
    keep = [True] * len(rec)
    if drop_frames:
        for _ in range(rng.randint(2, 6)):
            a = rng.randint(5, max(6, len(rec) - 10))
            for k in range(a, min(len(rec) - 1, a + rng.randint(2, 6))): keep[k] = False
    for k, (t, q, g, cur, qd) in enumerate(rec):
        if not keep[k]:
            continue
        joints = []
        for i in range(8):
            rmin, rmax = ranges[i]
            pn, gn = float(np.clip(norm(i, q[i]), 0, 1)), float(np.clip(norm(i, g[i]), 0, 1))
            joints.append({"range_min": rmin, "range_max": rmax,
                           "position": int(rmin + pn * (rmax - rmin)), "position_norm": pn,
                           "goal": int(rmin + gn * (rmax - rmin)), "goal_norm": gn,
                           "current_ma": int(cur[i]), "velocity": int(abs(qd[i]) / TICK)})
        rows.append({"episode_start_ns": t0, "global_frame_id": (ep_id * 10000 + k).to_bytes(4, "little"),
                     "timestamp_ns_since_episode_start": int(t * 1e9), "joints": joints, "images": []})
    return rows


WORLD = None


def one(args):
    ep_id, scen, seed = args
    global WORLD
    if WORLD is None:
        WORLD = World()
    rng = random.Random(seed)
    for attempt in range(20):
        try:
            extra_meta = {}
            if scen == "character":
                plan, cname, cmove = run_character(WORLD, rng)
                objs, target, extra, notes = [], None, {}, []
                extra_meta = {"name": cname, "move": cmove}
            else:
                plan, objs, target, extra, notes = build(WORLD, scen, rng)
            total = sum(k[0] for k in plan.keys) if plan else 0
            if scen == "slip":
                g_end = sum(k[0] for k in plan.keys[: next(i for i, k in enumerate(plan.keys) if k[2] == "relax grip") + 1])
                extra["slip_t"] = g_end + rng.uniform(1.0, 3.0)
            if scen == "overload":
                g_end = sum(k[0] for k in plan.keys[: next(i for i, k in enumerate(plan.keys) if k[2] == "relax grip") + 1])
                extra["fault_t"] = g_end + rng.uniform(0.8, 2.5); extra["fault_joint"] = 1
            if scen == "estop":
                extra["estop_t"] = rng.uniform(0.3, 0.8) * total
            sim_objs = []
            for o in objs:
                oo = dict(o); oo["pos"] = np.array(o["pos"]); oo["state"] = "table"
                sim_objs.append(oo)
            rec, events, T_end = simulate(WORLD, plan, sim_objs, scen, rng, extra)
            if scen in ("overload", "estop"):
                cut = next((e["t"] for e in events if e["type"] in ("overload", "estop")), None)
                if cut is not None:
                    rec = [r for r in rec if r[0] <= cut + rng.uniform(2.0, 3.5)]
                    events = [e for e in events if e["t"] <= cut + 3.5]
            delivered = [e for e in events if e["type"] == "release" and e.get("where") == "handover"]
            success = (scen not in ("character", "idle")) and len(delivered) >= (2 if scen == "two_parts" else 1)
            truth = {"id": ep_id, "scenario": scen, "difficulty": SCENARIOS[scen][1],
                     "task": target["task"] if target else None,
                     "objects": [{"name": o["name"], "width_mm": o["w"], "start_xy_mm": [round(o["start"][0] * 1000), round(o["start"][1] * 1000)]} for o in objs],
                     "operator_speed": round(plan.speed, 2) if plan else None,
                     "events": events, "success": success, "seconds": round(rec[-1][0], 1),
                     "character": extra_meta or None,
                     "narrative": narrative(scen, target, events, notes, success, extra_meta)}
            rows = to_rows(ep_id, rec, rng, scen == "frame_drops")
            for r in rows: r["task"] = truth["task"] or (f"act {extra_meta['name']} {extra_meta['move']}" if extra_meta else "stay still")
            return truth, rows
        except (ValueError, StopIteration):
            rng = random.Random(seed * 7919 + attempt + 1)
    if scen != "clean":                              # no reachable layout found: record a clean episode instead
        return one((ep_id, "clean", seed + 1))
    raise RuntimeError(f"episode {ep_id} ({scen}) failed 20 times")


def schema():
    import pyarrow as pa
    joint = pa.struct([("range_min", pa.uint32()), ("range_max", pa.uint32()), ("position", pa.uint32()),
                       ("position_norm", pa.float32()), ("goal", pa.uint32()), ("goal_norm", pa.float32()),
                       ("current_ma", pa.uint32()), ("velocity", pa.uint32())])
    return pa.schema([("episode_start_ns", pa.uint64()), ("global_frame_id", pa.binary()),
                      ("timestamp_ns_since_episode_start", pa.uint64()), ("joints", pa.list_(joint)),
                      ("images", pa.list_(pa.struct([("jpeg", pa.binary())]))), ("task", pa.string())])


def main():
    import pyarrow as pa, pyarrow.parquet as pq
    ap = argparse.ArgumentParser()
    ap.add_argument("--episodes", type=int, default=3000)
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "out")
    ap.add_argument("--workers", type=int, default=max(1, mp.cpu_count() - 1))
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--shard", type=int, default=100)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    total = sum(v[0] for v in SCENARIOS.values())
    jobs, k = [], 0
    for scen, (n, _) in SCENARIOS.items():
        for _ in range(round(n * a.episodes / total)):
            jobs.append([k, scen, a.seed * 100003 + k]); k += 1
    random.Random(a.seed).shuffle(jobs)
    for i, j in enumerate(jobs): j[0] = i
    t0 = time.time()
    with mp.Pool(a.workers) as pool, open(a.out / "truth.jsonl", "w") as tf:
        buf, shard = [], 0
        for n_done, (truth, rows) in enumerate(pool.imap(one, [tuple(j) for j in jobs], chunksize=4), 1):
            tf.write(json.dumps(truth) + "\n")
            buf.extend(rows)
            if n_done % a.shard == 0 or n_done == len(jobs):
                pq.write_table(pa.Table.from_pylist(buf, schema=schema()), a.out / f"episodes-{shard:03d}.parquet", compression="zstd")
                buf, shard = [], shard + 1
                print(f"{n_done}/{len(jobs)} episodes, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
