// Pick-and-place for the Character Studio: a few objects and a cup on the table in front of each arm.
// Every character finds the smallest object, picks it up and drops it in the cup, in its own servo settings.
// Robot frame: metres, Z up, the arm faces +Y, the table top is z = 0.
import * as THREE from 'three';
import { settings, simulate } from './engine.js';

export const CUP = { r: 0.028, h: 0.045, wall: 0.0025 };
// Spots on the table the arm reaches straight down to (checked with the IK). Neighbours sit > 6.5 cm apart.
export const SPOTS = [[-0.095, 0.14], [-0.05, 0.205], [0.02, 0.225], [0.085, 0.18], [0.105, 0.11]];
const JAW_OPEN = 0.0502, JAW_PER_RAD = 0.023;       // inner finger gap at j8 = 0, and how much each radian closes it
const KINDS = ['cube', 'ball', 'peg'];

function rng(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// width = what the jaws must span; height = how tall it stands; volume decides "smallest".
function shape(kind, s) {
  if (kind === 'cube') return { kind, size: s, width: s, height: s, volume: s ** 3 };
  if (kind === 'ball') return { kind, size: s, width: s, height: s, volume: (Math.PI / 6) * s ** 3 };
  return { kind, size: s, width: s, height: s * 1.4, volume: (Math.PI / 4) * s * s * s * 1.4 };   // peg: diameter s
}

/** Seed 0 is the opening layout; any other seed shuffles kinds, sizes and spots. */
export function layout(seed = 0) {
  if (seed === 0) {
    const items = [
      { ...shape('cube', 0.032), at: [0.02, 0.225], color: '#d9b35b' },
      { ...shape('ball', 0.036), at: [0.105, 0.11], color: '#5b8fd9' },
      { ...shape('peg', 0.014), at: [0.085, 0.18], color: '#d95b5b' },
    ];
    return finish(items, [-0.095, 0.14]);
  }
  const r = rng(seed * 7919);
  const spots = SPOTS.slice().sort(() => r() - 0.5);
  const sizes = [0.012 + r() * 0.006, 0.022 + r() * 0.006, 0.03 + r() * 0.008].sort(() => r() - 0.5);
  const colors = ['#d9b35b', '#5b8fd9', '#d95b5b', '#5bbf8a'].sort(() => r() - 0.5);
  const items = [0, 1, 2].map((i) => ({ ...shape(KINDS[Math.floor(r() * 3)], sizes[i]), at: spots[i + 1], color: colors[i] }));
  return finish(items, spots[0]);
}
function finish(items, cup) {
  items.forEach((it) => { it.yaw = Math.atan2(it.at[0], it.at[1]); });     // square to the arm, so the jaws meet flat faces
  const smallest = items.reduce((a, b) => (b.volume < a.volume ? b : a));
  return { items, cup, smallest: items.indexOf(smallest) };
}

/** Joint targets (rad) for the whole task, solved once with the IK on a hidden arm. */
export function planPick(arm, L, stand) {
  const it = L.items[L.smallest], [ox, oy] = it.at, [cx, cy] = L.cup;
  const down = new THREE.Vector3(0, 0, -1);
  const closeTo = Math.min(2.2, (JAW_OPEN - it.width + 0.0015) / JAW_PER_RAD);   // squeeze 1.5 mm
  const grabZ = Math.max(0.003, it.height / 2 - 0.009);
  const carryZ = CUP.h + it.height + 0.012;
  let seed = stand.slice();
  const at = (x, y, z, j8) => {
    const s = arm.solve(new THREE.Vector3(x, y, z), down, seed, stand);
    seed = s.q; const q = s.q.slice(); q[7] = j8; return q;
  };
  const look = (x, y, nod) => { const q = stand.slice(); q[0] = -Math.atan2(x, y); q[5] += nod; return q; };
  const above = at(ox, oy, grabZ + 0.06, 0);
  const grip = at(ox, oy, grabZ, 0);
  const lift = at(ox, oy, carryZ + 0.01, closeTo);
  seed = lift;
  const over = at(cx, cy, carryZ, closeTo);
  return {
    closeTo,
    keys: [
      // look over every object, then back to the smallest: that is the one
      ...L.items.map((o) => ({ q: look(o.at[0], o.at[1], 0.35), hold: 0.5, note: 'look' })),
      { q: look(ox, oy, 0.5), hold: 0.7, note: 'that one' },
      { q: above, hold: 0.1, note: 'reach' },
      { q: grip, hold: 0.15, note: 'down' },
      { q: [...grip.slice(0, 7), closeTo], hold: 0.35, note: 'grip' },
      { q: lift, hold: 0.1, note: 'lift' },
      { q: over, hold: 0.35, note: 'over the cup' },
      { q: [...over.slice(0, 7), 0], hold: 0.6, note: 'let go' },
      { q: stand, hold: 0.2, note: 'back' },
    ],
  };
}

/** One character performs the plan: servo frames, then where the object is in each frame. */
export function performPick(data, name, arm, L, P) {
  const E = data.engine, c = data.characters[name], { acc, speed } = settings(E, c);
  const v = (i, q) => (q - E.lo[i]) / (E.hi[i] - E.lo[i]);
  const steps = []; let t = 0.3;
  for (const k of P.keys) {
    steps.push({ t, goals: Object.fromEntries(k.q.map((q, i) => ['j' + (i + 1), v(i, q)])), acc, speed, wait: true });
    t += 0.05 + k.hold * c.tempo * 2;
  }
  const q = simulate(E, steps, data.stand, data.fps);
  return { q, obj: track(arm, L, P, q, data.fps), torque: null, peak: null };
}

// Object pose per frame: on the table, held once the jaws have closed on it, then dropped into the cup.
function track(arm, L, P, frames, fps) {
  const it = L.items[L.smallest];
  const rest = new THREE.Matrix4().compose(new THREE.Vector3(it.at[0], it.at[1], it.height / 2),
    new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), -it.yaw), new THREE.Vector3(1, 1, 1));
  const gb = arm.gb, out = [];
  let state = 'table', rel = null, fall = null, cur = rest.clone();
  for (const q of frames) {
    if (state === 'table' && q[7] > P.closeTo - 0.06) {
      arm.fk(q); rel = gb.matrixWorld.clone().invert().multiply(rest); state = 'held';
    } else if (state === 'held' && q[7] < P.closeTo - 0.25) {
      state = 'fall'; fall = { p: new THREE.Vector3().setFromMatrixPosition(cur), v: 0, quat: new THREE.Quaternion().setFromRotationMatrix(cur) };
    }
    if (state === 'held') { arm.fk(q); cur = gb.matrixWorld.clone().multiply(rel); }
    if (state === 'fall') {
      const floor = CUP.wall + it.height / 2;
      fall.v += 9.81 / fps; fall.p.z = Math.max(floor, fall.p.z - fall.v / fps);
      fall.p.x += (L.cup[0] - fall.p.x) * 0.25; fall.p.y += (L.cup[1] - fall.p.y) * 0.25;   // the cup walls funnel it in
      cur = new THREE.Matrix4().compose(fall.p, fall.quat, new THREE.Vector3(1, 1, 1));
    }
    out.push(cur.elements.slice());
  }
  arm.setQ(arm.q); arm.r.root.updateMatrixWorld(true);
  return out;
}

/* ---------- three.js props: the objects, the cup and a ring marking the smallest ---------- */
export function buildProps(L, ringColor) {
  const g = new THREE.Group();
  const meshes = L.items.map((it) => {
    const mat = new THREE.MeshStandardMaterial({ color: it.color, roughness: 0.55 });
    const geo = it.kind === 'cube' ? new THREE.BoxGeometry(it.size, it.size, it.size)
      : it.kind === 'ball' ? new THREE.SphereGeometry(it.size / 2, 28, 18)
      : new THREE.CylinderGeometry(it.size / 2, it.size / 2, it.height, 24).rotateX(Math.PI / 2);
    const m = new THREE.Mesh(geo, mat);
    m.position.set(it.at[0], it.at[1], it.height / 2); m.rotation.z = -it.yaw;
    m.matrixAutoUpdate = true; g.add(m); return m;
  });
  const { r, h, wall } = CUP;
  const prof = [[0, 0], [r - 0.002, 0], [r, 0.002], [r + 0.002, h], [r + 0.002 - wall, h], [r - wall, wall], [0, wall]]
    .map(([x, y]) => new THREE.Vector2(x, y));
  const cup = new THREE.Mesh(new THREE.LatheGeometry(prof, 40).rotateX(Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: '#eef1f4', roughness: 0.35, side: THREE.DoubleSide }));
  cup.position.set(L.cup[0], L.cup[1], 0); g.add(cup);
  // a C-shaped handle on the side away from the arm
  const hg = new THREE.TorusGeometry(0.012, 0.0028, 10, 24, Math.PI).rotateZ(-Math.PI / 2).rotateX(Math.PI / 2);
  const handle = new THREE.Mesh(hg, cup.material);
  const ang = Math.atan2(L.cup[1], L.cup[0]);
  handle.position.set(L.cup[0] + Math.cos(ang) * (r - 0.001), L.cup[1] + Math.sin(ang) * (r - 0.001), h * 0.5);
  handle.rotation.z = ang;
  g.add(handle);
  const s = L.items[L.smallest];
  const ring = new THREE.Mesh(new THREE.RingGeometry(s.width * 0.75 + 0.004, s.width * 0.75 + 0.007, 40),
    new THREE.MeshBasicMaterial({ color: ringColor, side: THREE.DoubleSide }));
  ring.position.set(s.at[0], s.at[1], 0.0005); g.add(ring);
  return { group: g, meshes, target: meshes[L.smallest], ring };
}

/* ---------- wave hello: hand up, open jaws, wrist swings side to side ---------- */
// j1 is not a joint angle in this clip: it carries a 0..1 envelope, and the page multiplies it by the
// yaw that points the arm at the camera, so every arm turns to whoever is watching, wherever they orbit.
export const WAVE_UP = [0, 0.2, -1.5, 0.2, 1.57, 0, 0, 0];
export function performWave(data, name, cycles = 3) {
  const E = data.engine, c = data.characters[name], { acc, speed } = settings(E, c);
  const v = (i, q) => (q - E.lo[i]) / (E.hi[i] - E.lo[i]);
  const goals = (q) => Object.fromEntries(q.map((x, i) => ['j' + (i + 1), v(i, x)]));
  const stand = data.stand, amp = 0.5 * Math.min(1.4, Math.max(0.5, c.size));
  const up = WAVE_UP.slice(); up[0] = 1;
  const steps = []; let t = 0.3;
  const push = (q, dt, wait) => { steps.push({ t, goals: goals(q), acc, speed, wait }); t += dt; };
  push(up, 0.1, true);                                        // rise and turn to you
  const half = Math.max(0.22, 0.32 * c.tempo * 1.6);
  for (let k = 0; k < cycles * 2; k++) {
    const q = up.slice(); q[5] = (k % 2 ? -1 : 1) * amp; push(q, half, false);
  }
  const hold = up.slice(); push(hold, 0.4 * c.tempo * 2, true);
  const q = data.stand.slice(); q[0] = 0;
  push(q, 0.1, true);
  return { q: simulate(E, steps, [0, ...stand.slice(1)], data.fps), torque: null, peak: null, yawEnvelope: true };
}
