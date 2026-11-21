"""ElRobot + STS3215 servo simulation: which acc/speed/stepping settings give the lowest latency
without overloading the joints?

Arm: real ElRobot URDF (norma-core) masses/inertias, gravity, +30 g cup in the gripper.
Servo (each joint, STS3215 12 V): firmware profile generator (speed limit + acc ramp, acc unit
100 ticks/s^2, speed in ticks/s), P-D position loop -> PWM duty, DC motor with gearbox:
torque = 2.94 N*m * (duty - w / 4.71 rad/s), reflected rotor inertia (armature) and gear friction.
Uncertain servo internals are swept (Kp, armature) to check the ranking holds.
"""
import re, sys, math, itertools, json
import numpy as np
import mujoco

TICK = 2 * math.pi / 4096           # rad per tick
STALL, W0 = 2.94, 4.71              # N*m, rad/s (URDF effort/velocity = STS3215 12 V datasheet)
DT = 0.0005

import pathlib
_U = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith('.urdf') else pathlib.Path(__file__).resolve().parent / 'elrobot.urdf'
urdf = open(_U).read()
urdf = re.sub(r'<visual>.*?</visual>', '', urdf, flags=re.S)
urdf = re.sub(r'<collision>.*?</collision>', '', urdf, flags=re.S)
urdf = re.sub(r'<joint name="rev_motor_08_[12]" type="prismatic">', lambda m: m.group(0).replace('prismatic', 'fixed'), urdf)
# +30 g cup at the gripper
urdf = re.sub(r'(<link name="Gripper_Base_v1_1">\s*<inertial>.*?<mass value=")([\d.eE-]+)',
              lambda m: m.group(1) + str(float(m.group(2)) + 0.030), urdf, flags=re.S)
urdf = urdf.replace('<robot name="Elrobot" >', '<robot name="Elrobot" ><mujoco><compiler discardvisual="true" fusestatic="false" balanceinertia="true" boundmass="1e-4" boundinertia="1e-7"/></mujoco>')

JN = [f"rev_motor_0{i}" for i in range(1, 9)]

def build(armature, servo_mass=None):
    u = urdf
    if servo_mass:   # real STS3215 is ~55 g; the CAD URDF says 32 g
        u = re.sub(r'(<link name="ST3215_\d_v1_1">\s*<inertial>.*?<mass value=")([\d.eE-]+)',
                   lambda m: m.group(1) + str(servo_mass), u, flags=re.S)
    spec = mujoco.MjSpec.from_string(u)
    spec.option.timestep = DT
    spec.option.gravity = [0, 0, -9.81]
    for j in spec.joints:
        if j.name in JN:
            j.armature = armature
            j.frictionloss = 0.03
            j.range = j.range  # keep
    m = spec.compile()
    return m

def jidx(m):
    return [m.joint(n).qposadr[0] for n in JN], [m.joint(n).dofadr[0] for n in JN]

class Servo:
    """STS3215 firmware model for one joint."""
    def __init__(self, q0, kp, kd):
        self.sp = q0; self.v = 0.0; self.goal = q0
        self.speed = 600 * TICK; self.acc = 20 * 100 * TICK; self.kp, self.kd = kp, kd
    def set(self, goal, speed=None, acc=None):
        self.goal = goal
        if speed is not None: self.speed = (speed if speed > 0 else 3400) * TICK
        if acc is not None: self.acc = (acc * 100 if acc > 0 else 1e9) * TICK
    def step(self, q, qd):
        # trapezoidal profile toward goal (accelerate, cruise, decelerate)
        err = self.goal - self.sp
        dstop = self.v * self.v / (2 * self.acc)
        if abs(err) < 1e-6 and abs(self.v) < 1e-3:
            self.v = 0.0
        else:
            want = math.copysign(self.speed, err)
            if abs(err) <= dstop + abs(self.v) * DT and self.v * err > 0:
                want = 0.0
            dv = max(-self.acc * DT, min(self.acc * DT, want - self.v))
            self.v += dv
            self.sp += self.v * DT
            if (self.goal - self.sp) * err < 0:   # passed the goal
                self.sp, self.v = self.goal, 0.0
        # position loop on the quantized encoder
        e = round((self.sp - q) / TICK) * TICK
        duty = max(-1.0, min(1.0, self.kp * e - self.kd * qd))
        return STALL * (duty - qd / W0), duty

# poses (rad): a reaching pose that loads the shoulder, used as the start of every test
REACH = [0.0, 0.7, -0.9, 0.2, 0.0, 0.4, 0.0, 0.3]

def run(m, kp, kd, joint, delta, speed, acc, stepped=False, step_norm=0.04, dt_step=0.12, T=2.5):
    d = mujoco.MjData(m)
    qa, da = jidx(m)
    for i, a in enumerate(qa): d.qpos[a] = REACH[i]
    mujoco.mj_forward(m, d)
    servos = [Servo(REACH[i], kp, kd) for i in range(8)]
    # settle 0.5 s holding the pose
    for _ in range(int(0.5 / DT)):
        for i in range(8):
            tau, _ = servos[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
        mujoco.mj_step(m, d)
    j = joint; q0 = d.qpos[qa[j]]; target = REACH[j] + delta
    lo, hi = m.jnt_range[m.joint(JN[j]).id]
    span = hi - lo
    servos[j].set(servos[j].goal, speed, acc)
    # command schedule: one shot, or elrobot.py-style slices of step_norm*span every dt_step
    if stepped:
        n = max(1, math.ceil(abs(delta) / (step_norm * span)))
        sched = [(k * dt_step, REACH[j] + delta * (k + 1) / n) for k in range(n)]
    else:
        sched = [(0.0, target)]
    t = 0.0; si = 0
    first_move = settle = None; peak = 0.0; over80 = 0.0; overshoot = 0.0; inside_since = None
    sign = 1 if delta > 0 else -1
    while t < T:
        while si < len(sched) and t >= sched[si][0]:
            servos[j].set(sched[si][1]); si += 1
        for i in range(8):
            tau, _ = servos[i].step(d.qpos[qa[i]], d.qvel[da[i]]); d.qfrc_applied[da[i]] = tau
            if i == j:
                peak = max(peak, abs(tau) / STALL)
                if abs(tau) > 0.8 * STALL: over80 += DT
        mujoco.mj_step(m, d); t += DT
        q = d.qpos[qa[j]]
        if first_move is None and abs(q - q0) >= 5 * TICK: first_move = t
        overshoot = max(overshoot, sign * (q - target))
        if abs(q - target) <= math.radians(1.0) and si == len(sched):
            if inside_since is None: inside_since = t
            if settle is None and t - inside_since > 0.05: settle = inside_since
        else:
            inside_since = None
            if settle is not None and abs(q - target) > math.radians(1.5): settle = None
    return dict(first_ms=None if first_move is None else first_move * 1000,
                settle_ms=None if settle is None else settle * 1000,
                peak=peak, over80_ms=over80 * 1000, overshoot_deg=math.degrees(max(0.0, overshoot)))

if __name__ == "__main__":
    out = []
    TESTS = [("j2 shoulder lift 20°", 1, math.radians(-20)),
             ("j3 elbow 20°", 2, math.radians(20)),
             ("j5 wrist pitch 20°", 4, math.radians(20)),
             ("j7 wrist rotate 30°", 6, math.radians(30)),
             ("j8 jaws 30°", 7, math.radians(30))]
    ACCS = [10, 20, 30, 50, 80, 100, 150, 254, 0]
    SPEEDS = [500, 600, 900, 1500]
    variants = [("base", dict(kp=1 / (40 * TICK), kd=0.05, arm=0.010)),
                ("kp_lo", dict(kp=1 / (80 * TICK), kd=0.05, arm=0.010)),
                ("kp_hi", dict(kp=1 / (20 * TICK), kd=0.05, arm=0.010)),
                ("arm_lo", dict(kp=1 / (40 * TICK), kd=0.05, arm=0.004)),
                ("arm_hi", dict(kp=1 / (40 * TICK), kd=0.05, arm=0.020)),
                ("heavy", dict(kp=1 / (40 * TICK), kd=0.05, arm=0.010, sm=0.055))]
    models = {}
    for vname, v in variants:
        key = (v["arm"], v.get("sm"))
        if key not in models: models[key] = build(v["arm"], v.get("sm"))
        m = models[key]
        for name, j, delta in TESTS:
            for acc, speed in itertools.product(ACCS, SPEEDS):
                if vname != "base" and speed != 600: continue
                for stepped in (False, True):
                    if stepped and (acc not in (20, 50, 100) or speed != 600): continue
                    r = run(m, v["kp"], v["kd"], j, delta, speed, acc, stepped)
                    r.update(variant=vname, test=name, joint=j, acc=acc, speed=speed, stepped=stepped)
                    out.append(r)
        print(vname, "done", file=sys.stderr)
    json.dump(out, open(sys.argv[2], "w"), indent=1)
