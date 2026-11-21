// Third Hand characters for JavaScript (browser or Node, no dependencies).
// Planner: the same rules as the Python package (thc/planner.py). Servo model: the STS3215 speed +
// acceleration ramp, so you can preview or animate a character's motion in joint angles (radians).
//
//   import { plan, perform, sanitize } from './thc.js';
//   const data = await (await fetch('../characters.json')).json();     // or JSON.parse(fs.readFileSync(...))
//   const steps = plan(data.engine, data.characters.trickster, data.engine.gestures.kick_ball);
//   const frames = perform(data, 'trickster', data.engine.gestures.kick_ball);   // [[j1..j8 rad], ...] at data.fps
//
// Note: tremor uses a different random generator than Python, so nervous/shy tremor values differ slightly.
// Planner: same rules as character.plan / _smooth_plan. Servo: the firmware's speed + acceleration
// ramp (exact port of servo_sim.Servo's profile), then the joint follows the setpoint with a lag
// fitted to the physics clips: mean 0.4 deg.

const JOINTS = ['j1', 'j2', 'j3', 'j4', 'j5', 'j6', 'j7', 'j8'];
const TICK = (2 * Math.PI) / 4096;
const W0 = 4.71;                    // rad/s, STS3215 12 V no-load speed
export const TAU = 0.01;            // s, joint lag behind the setpoint (fitted to the physics clips: mean 0.36°)
const DT = 0.001;

function rng(seed) {                // mulberry32, deterministic tremor
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

export function settings(E, c) {
  const acc = {}, speed = {};
  for (const j of JOINTS) {
    const am = j === 'j2' ? Math.min(c.acc_mult, 1) : c.acc_mult;
    acc[j] = Math.trunc(Math.max(5, Math.min(E.acc_cap[j], E.base[j][0] * am)));
    speed[j] = Math.trunc(Math.max(100, Math.min(E.speed_cap[j], E.base[j][1] * c.speed_mult)));
  }
  return { acc, speed };
}

const clampJ = (E, j, v) => {
  const n = E.neutral[j], lo = n - E.max_dev[j], hi = n + E.max_dev[j];
  return Math.max(0, Math.min(1, Math.max(lo, Math.min(hi, v))));
};

export function stance(E, c) {
  const s = {};
  for (const j of JOINTS) s[j] = clampJ(E, j, E.neutral[j] + E.sign[j] * (c.posture[j] || 0));
  return s;
}

const minJerk = (x) => { x = Math.max(0, Math.min(1, x)); return x * x * x * (10 - 15 * x + 6 * x * x); };

/** keyframes: [[beats, {j: offset_in_units}], ...] — the same format as character.GESTURES. */
export function plan(E, c, keyframes, seed = 0) {
  const { acc, speed } = settings(E, c);
  const base = stance(E, c);
  let cur = { ...base }, t = 0;
  const steps = [];
  const targetOf = (offs) => {
    const tg = { ...cur };
    for (const [j, o] of Object.entries(offs)) if (JOINTS.includes(j)) tg[j] = clampJ(E, j, base[j] + E.sign[j] * o * E.unit * c.size);
    return tg;
  };
  if (c.smooth) {
    const rate = 20;
    const keys = [...keyframes, [1.5, Object.fromEntries(JOINTS.map((j) => [j, 0]))]];
    for (const [beats, offs] of keys) {
      const dur = beats * c.tempo, tg = targetOf(offs);
      const moved = JOINTS.filter((j) => Math.abs(tg[j] - cur[j]) > 1e-4);
      const n = Math.max(1, Math.round(dur * rate));
      for (let k = 1; k <= n; k++) {
        const f = minJerk(k / n), goals = {};
        for (const j of moved) goals[j] = cur[j] + (tg[j] - cur[j]) * f;
        if (moved.length || k === n) steps.push({ t: t + k / rate, goals, acc, speed, wait: false });
      }
      t += n / rate; cur = tg;
    }
    steps.push({ t, goals: { ...base }, acc, speed, wait: true });
    return steps;
  }
  const r = rng(seed + 1);
  for (const [beats, offs] of keyframes) {
    let dur = beats * c.tempo;
    const tg = targetOf(offs);
    const moved = JOINTS.filter((j) => Math.abs(tg[j] - cur[j]) > 1e-4);
    if (moved.length && c.anticipation > 0 && Math.max(...moved.map((j) => Math.abs(tg[j] - cur[j]))) > 0.03) {
      const pre = {}; for (const j of moved) pre[j] = clampJ(E, j, cur[j] - c.anticipation * (tg[j] - cur[j]));
      steps.push({ t, goals: pre, acc, speed, wait: false }); t += 0.25 * dur; dur *= 0.75;
    }
    if (moved.length && c.overshoot > 0) {
      const ov = {}; for (const j of moved) ov[j] = clampJ(E, j, tg[j] + c.overshoot * (tg[j] - cur[j]));
      steps.push({ t, goals: ov, acc, speed, wait: false }); t += 0.45 * dur; dur *= 0.55;
    }
    const goals = {}; for (const j of moved) goals[j] = tg[j];
    if (c.tremor) for (const j of ['j6', 'j7']) goals[j] = clampJ(E, j, tg[j] + (r() * 2 - 1) * c.tremor);
    steps.push({ t, goals, acc, speed, wait: c.blend === 0 && moved.length > 0 });
    t += c.blend ? dur * (1 - c.blend) : dur;
    cur = tg;
  }
  steps.push({ t, goals: { ...base }, acc, speed, wait: true });
  return steps;
}

class Servo {                       // exact port of servo_sim.Servo's profile generator
  constructor(q0) { this.sp = q0; this.v = 0; this.goal = q0; this.speed = 600 * TICK; this.acc = 2000 * TICK; }
  set(goal, speed, acc) {
    this.goal = goal;
    if (speed != null) this.speed = (speed > 0 ? speed : 3400) * TICK;
    if (acc != null) this.acc = (acc > 0 ? acc * 100 : 1e9) * TICK;
  }
  step(dt) {
    const err = this.goal - this.sp, dstop = (this.v * this.v) / (2 * this.acc);
    if (Math.abs(err) < 1e-6 && Math.abs(this.v) < 1e-3) { this.v = 0; return; }
    let want = Math.sign(err) * this.speed;
    if (Math.abs(err) <= dstop + Math.abs(this.v) * dt && this.v * err > 0) want = 0;
    this.v += Math.max(-this.acc * dt, Math.min(this.acc * dt, want - this.v));
    this.sp += this.v * dt;
    if ((this.goal - this.sp) * err < 0) { this.sp = this.goal; this.v = 0; }
  }
}

/** Play planned steps on the servo model; returns joint angles (rad) at fps, like the physics clips. */
export function simulate(E, steps, stand, fps = 30, tau = TAU) {
  const toRad = (i, v) => E.lo[i] + v * (E.hi[i] - E.lo[i]);
  const sv = stand.map((q) => new Servo(q)), q = [...stand];
  const frames = [];
  const every = Math.round(1 / (fps * DT));
  let t = 0, k = 0, shift = 0, waiting = null, wstart = 0, n = 0;
  const a = 1 - Math.exp(-DT / tau);
  while (true) {
    if (waiting && (Object.entries(waiting).every(([i, v]) => Math.abs(q[i] - toRad(+i, v)) < 0.0262) || t - wstart > 2)) { shift += t - wstart; waiting = null; }
    while (!waiting && k < steps.length && t >= steps[k].t + shift) {
      const s = steps[k];
      for (const [j, v] of Object.entries(s.goals)) { const i = +j.slice(1) - 1; sv[i].set(toRad(i, v), s.speed[j], s.acc[j]); }
      if (s.wait) { waiting = Object.fromEntries(Object.entries(s.goals).map(([j, v]) => [+j.slice(1) - 1, v])); wstart = t; }
      k++;
    }
    let moving = 0;
    for (let i = 0; i < 8; i++) {
      sv[i].step(DT);
      let dq = (sv[i].sp - q[i]) * a;
      dq = Math.max(-W0 * DT, Math.min(W0 * DT, dq));
      q[i] += dq; moving = Math.max(moving, Math.abs(dq / DT));
    }
    if (n % every === 0) frames.push(q.map((x) => Math.round(x * 1e4) / 1e4));
    t += DT; n++;
    if (k >= steps.length && !waiting && t > steps[steps.length - 1].t + shift + 0.6 && moving < 0.02) break;
    if (t > 40) break;
  }
  for (let i = 0; i < Math.round(0.4 * fps); i++) frames.push(frames[frames.length - 1]);
  return frames;
}

/** Everything at once: one character performs keyframes -> frames. */
export function perform(data, name, keyframes, seed = 0) {
  const E = data.engine, c = data.characters[name];
  return simulate(E, plan(E, c, keyframes, seed), data.stand ?? data.stand_rad, data.fps);
}

/** Validate Claude's choreography: keep known joints, finite numbers, sane beats and ranges. */
export function sanitize(E, raw) {
  const out = [];
  const list = Array.isArray(raw?.keyframes) ? raw.keyframes : Array.isArray(raw) ? raw : [];
  for (const kf of list.slice(0, 24)) {
    const beats = Number(kf?.beats);
    if (!Number.isFinite(beats)) continue;
    const pose = {};
    for (const [j, v] of Object.entries(kf?.pose || {})) {
      const x = Number(v);
      if (!JOINTS.includes(j) || !Number.isFinite(x)) continue;
      const lim = E.max_dev[j] / E.unit;                 // the planner clamps again; this keeps notes honest
      pose[j] = Math.max(-lim, Math.min(lim, x));
    }
    out.push({ beats: Math.max(0.2, Math.min(4, beats)), pose, note: String(kf?.note || '').slice(0, 60) });
  }
  return out;
}
