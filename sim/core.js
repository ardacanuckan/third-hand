// Third Hand — robot core: URDF loading, forward kinematics, IK, bench layout.
// The ElRobot URDF and meshes come from github.com/norma-core/norma-core (hardware/elrobot/simulation).
import * as THREE from 'three';

/* ---------- bench layout, robot frame: metres, Z up, robot faces +Y, +X is the robot's right ---------- */
export const LAYOUT = {
  // SOL-MIO v1.3 on standoffs, turned 180° so its power corner (J2, U1, D1) sits nearest the arm.
  // origin = the board point (Altium mm) that lands on `center`.
  pcb: { center: [0.0356, 0.187, 0.026], size: [0.0976, 0.1, 0.0016], origin: [48.3, 50] },
  tray: {
    center: [-0.135, 0.112],
    slots: { A1: [-0.175, 0.135], A2: [-0.135, 0.135], A3: [-0.095, 0.135],
             B1: [-0.175, 0.09],  B2: [-0.135, 0.09],  B3: [-0.095, 0.09] },
    cupH: 0.03, cupR: 0.0135,
  },
  handover: [0.135, 0.15],
  ironStand: [0.19, 0.37],
  sideCam: { pos: [0.36, -0.02, 0.33], look: [-0.01, 0.15, 0.02] },
};

// The power stage of a fresh SOL-MIO v1.3 board: 12 V jack J2 → D2 → VIN (C4, C13) → 7805 → 5 V → R1 → power LED D1.
// Positions are the board's own Altium coordinates in mm (y up). Live on the bench: the SMD parts, smallest first.
export const PARTS = [
  { ref: 'D2',  slot: 'A1', kind: 'sod323',  at: [82.0, 90.9], a: 90, pads: [[82.0, 92.15], [82.0, 89.65]] },
  { ref: 'R1',  slot: 'A2', kind: 'r0603',   at: [87.6, 83.6], a: 0,  pads: [[86.85, 83.6], [88.35, 83.6]] },
  { ref: 'D1',  slot: 'A3', kind: 'led1206', at: [93.1, 83.6], a: 0,  pads: [[91.6, 83.6], [94.6, 83.6]] },
  { ref: 'C4',  slot: 'B1', kind: 'vchip',   at: [74.7, 93.1], a: 90, pads: [[74.7, 96.5], [74.7, 89.7]] },
  { ref: 'C13', slot: 'B2', kind: 'vchip',   at: [55.8, 93.1], a: 90, pads: [[55.8, 96.5], [55.8, 89.7]] },
];
// Through-hole parts are soldered from the underside, so they are fitted before the board goes on the fixture.
export const PREFIT = [
  { ref: 'U1', kind: 'to220', at: [78.2, 81.3], a: 0 },
  { ref: 'J2', kind: 'jack',  at: [92.6, 93.5], a: 90 },
];

/* ---------- tiny URDF reader (enough for this exporter's output) ---------- */
const attr = (s, n) => { const m = s && s.match(new RegExp('\\b' + n + '="([^"]*)"')); return m ? m[1] : null; };
const nums = (s, d) => (s ?? d).trim().split(/\s+/).map(Number);
const tag = (body, t) => { const m = body.match(new RegExp('<' + t + '\\b([^>]*)/?>')); return m ? m[1] : null; };

export function parseURDF(text) {
  const links = [];
  for (const m of text.matchAll(/<link\s+name="([^"]+)"\s*>([\s\S]*?)<\/link>/g)) {
    const vis = m[2].match(/<visual>([\s\S]*?)<\/visual>/);
    let visual = null;
    if (vis) {
      const o = tag(vis[1], 'origin'), mesh = tag(vis[1], 'mesh');
      visual = { xyz: nums(attr(o, 'xyz'), '0 0 0'), rpy: nums(attr(o, 'rpy'), '0 0 0'),
                 file: attr(mesh, 'filename').split('/').pop(), material: attr(tag(vis[1], 'material'), 'name') };
    }
    links.push({ name: m[1], visual });
  }
  const joints = [];
  for (const m of text.matchAll(/<joint\s+name="([^"]+)"\s+type="([^"]+)"\s*>([\s\S]*?)<\/joint>/g)) {
    const b = m[3], o = tag(b, 'origin'), lim = tag(b, 'limit'), mim = tag(b, 'mimic');
    joints.push({
      name: m[1], type: m[2], parent: attr(tag(b, 'parent'), 'link'), child: attr(tag(b, 'child'), 'link'),
      xyz: nums(attr(o, 'xyz'), '0 0 0'), rpy: nums(attr(o, 'rpy'), '0 0 0'), axis: nums(attr(tag(b, 'axis'), 'xyz'), '1 0 0'),
      lower: lim ? +attr(lim, 'lower') : 0, upper: lim ? +attr(lim, 'upper') : 0,
      mimic: mim ? { joint: attr(mim, 'joint'), mul: +(attr(mim, 'multiplier') ?? 1), off: +(attr(mim, 'offset') ?? 0) } : null,
    });
  }
  return { links, joints };
}

function b64bytes(b64) {
  if (typeof atob === 'function') {
    const s = atob(b64), u = new Uint8Array(s.length);
    for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i);
    return u;
  }
  return new Uint8Array(Buffer.from(b64, 'base64'));
}

export function decodeMesh(m, q) {
  const vb = b64bytes(m.v), ib = b64bytes(m.i);
  const v16 = new Int16Array(vb.buffer, vb.byteOffset, vb.byteLength / 2);
  const pos = new Float32Array(v16.length), k = q * 0.001;
  for (let i = 0; i < v16.length; i++) pos[i] = v16[i] * k;
  const idx = m.u32 ? new Uint32Array(ib.buffer, ib.byteOffset, ib.byteLength / 4)
                    : new Uint16Array(ib.buffer, ib.byteOffset, ib.byteLength / 2);
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.computeVertexNormals();
  g.computeBoundingBox();
  return g;
}

const rpyQuat = (r) => new THREE.Quaternion().setFromEuler(new THREE.Euler(r[0], r[1], r[2], 'ZYX'));
const _q = new THREE.Quaternion(), _v = new THREE.Vector3();

export function buildRobot(data, materialFor) {
  const { links, joints } = parseURDF(data.urdf);
  const L = {};
  for (const l of links) {
    const g = new THREE.Group(); g.name = l.name;
    if (l.visual) {
      const mesh = new THREE.Mesh(decodeMesh(data.meshes[l.visual.file], data.q), materialFor(l.name, l.visual.material));
      mesh.position.fromArray(l.visual.xyz); mesh.quaternion.copy(rpyQuat(l.visual.rpy));
      mesh.castShadow = true; mesh.receiveShadow = true;
      g.add(mesh); g.userData.mesh = mesh;
    }
    L[l.name] = g;
  }
  const J = {}, children = new Set();
  for (const j of joints) {
    const o = new THREE.Object3D(); o.name = 'joint:' + j.name;
    const q0 = rpyQuat(j.rpy); o.position.fromArray(j.xyz); o.quaternion.copy(q0);
    L[j.parent].add(o); o.add(L[j.child]); children.add(j.child);
    J[j.name] = { ...j, obj: o, q0, p0: o.position.clone(), ax: new THREE.Vector3().fromArray(j.axis).normalize(), value: 0 };
  }
  const apply = (j, v) => {
    j.value = v;
    if (j.type === 'revolute' || j.type === 'continuous') j.obj.quaternion.copy(j.q0).multiply(_q.setFromAxisAngle(j.ax, v));
    else if (j.type === 'prismatic') j.obj.position.copy(j.p0).add(_v.copy(j.ax).applyQuaternion(j.q0).multiplyScalar(v));
  };
  const followers = Object.values(J).filter((j) => j.mimic);
  const set = (name, v) => {
    apply(J[name], v);
    for (const f of followers) if (f.mimic.joint === name) apply(f, v * f.mimic.mul + f.mimic.off);
  };
  const rootName = links.map((l) => l.name).find((n) => !children.has(n));
  return { root: L[rootName], links: L, joints: J, set };
}

/* ---------- arm: tool frame, FK, damped-least-squares IK ---------- */
export const JOINTS = ['rev_motor_01', 'rev_motor_02', 'rev_motor_03', 'rev_motor_04', 'rev_motor_05', 'rev_motor_06', 'rev_motor_07', 'rev_motor_08'];
const IK_JOINTS = [0, 1, 2, 3, 5]; // yaw + four pitch joints; j5 (forearm roll) and j7 (wrist roll) stay put

function solveLinear(A, b) {
  const n = b.length, M = A.map((r, i) => [...r, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    for (let r = c + 1; r < n; r++) {
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  const x = new Array(n).fill(0);
  for (let r = n - 1; r >= 0; r--) {
    let s = M[r][n];
    for (let k = r + 1; k < n; k++) s -= M[r][k] * x[k];
    x[r] = s / M[r][r];
  }
  return x;
}

export class Arm {
  constructor(robot) {
    this.r = robot;
    this.lim = JOINTS.map((n) => [robot.joints[n].lower, robot.joints[n].upper]);
    this.q = JOINTS.map(() => 0);
    this.gb = robot.links['Gripper_Base_v1_1'];
    this.setQ(this.q);
    robot.root.updateMatrixWorld(true);
    // Tool axis = the wrist-roll axis, pointing out through the jaws.
    this.axisLocal = robot.joints['rev_motor_07'].ax.clone().negate();
    const jaws = new THREE.Box3()
      .setFromObject(robot.links['Gripper_Jaw_01_v1_1'])
      .union(new THREE.Box3().setFromObject(robot.links['Gripper_Jaw_02_v1_1']));
    const c = jaws.getCenter(new THREE.Vector3());
    const gbW = this.gb.getWorldPosition(new THREE.Vector3());
    let ext = -1;
    for (const x of [jaws.min.x, jaws.max.x]) for (const y of [jaws.min.y, jaws.max.y]) for (const z of [jaws.min.z, jaws.max.z])
      ext = Math.max(ext, new THREE.Vector3(x, y, z).sub(c).dot(this.axisLocal));
    // At the zero pose every link frame is aligned with the robot frame, so world offsets are local offsets.
    this.tipLocal = c.clone().sub(gbW).addScaledVector(this.axisLocal, ext - 0.004);
    this.jawCentreLocal = c.clone().sub(gbW);
  }
  setQ(q) { JOINTS.forEach((n, i) => this.r.set(n, q[i])); }
  fk(q) {
    this.setQ(q);
    this.r.root.updateMatrixWorld(true);
    return {
      tip: this.gb.localToWorld(this.tipLocal.clone()),
      axis: this.axisLocal.clone().transformDirection(this.gb.matrixWorld),
    };
  }
  // Positions are in the robot root's parent frame (the bench). Restores the displayed pose afterwards.
  solve(target, axisT = new THREE.Vector3(0, 0, -1), seed = this.q, rest = null, w = 0.12) {
    const q = seed.slice(), lam2 = 0.0004, h = 1e-4;
    let pe = 1, ae = 1;
    for (let it = 0; it < 240; it++) {
      const { tip, axis } = this.fk(q);
      const e = [target.x - tip.x, target.y - tip.y, target.z - tip.z, w * (axisT.x - axis.x), w * (axisT.y - axis.y), w * (axisT.z - axis.z)];
      pe = Math.hypot(e[0], e[1], e[2]); ae = Math.hypot(e[3], e[4], e[5]) / w;
      if (pe < 2e-4 && ae < 4e-3) break;
      const cols = IK_JOINTS.map((k) => {
        const qq = q.slice(); qq[k] += h;
        const f = this.fk(qq);
        return [(f.tip.x - tip.x) / h, (f.tip.y - tip.y) / h, (f.tip.z - tip.z) / h,
                w * (f.axis.x - axis.x) / h, w * (f.axis.y - axis.y) / h, w * (f.axis.z - axis.z) / h];
      });
      const A = [...Array(6)].map((_, r) => [...Array(6)].map((_, c) => cols.reduce((s, col) => s + col[r] * col[c], 0) + (r === c ? lam2 : 0)));
      const y = solveLinear(A, e);
      let dq = cols.map((col) => col.reduce((s, v, r) => s + v * y[r], 0));
      if (rest) {
        // nudge towards the rest pose inside the null space (keeps the elbow tidy)
        const z = IK_JOINTS.map((k) => 0.08 * (rest[k] - q[k]));
        const Jz = [...Array(6)].map((_, r) => cols.reduce((s, col, i) => s + col[r] * z[i], 0));
        const yz = solveLinear(A, Jz);
        dq = dq.map((d, i) => d + z[i] - cols[i].reduce((s, v, r) => s + v * yz[r], 0));
      }
      const m = Math.max(...dq.map(Math.abs));
      const s = m > 0.2 ? 0.2 / m : 1;
      IK_JOINTS.forEach((k, i) => { q[k] = Math.min(this.lim[k][1], Math.max(this.lim[k][0], q[k] + dq[i] * s)); });
    }
    this.setQ(this.q);
    this.r.root.updateMatrixWorld(true);
    return { q, pe, ae };
  }
}

// Board millimetres (Altium coordinates) -> bench metres. The board is turned 180°.
export function boardToBench(x, y, z = 0) {
  const c = LAYOUT.pcb.center, o = LAYOUT.pcb.origin;
  return new THREE.Vector3(c[0] - (x - o[0]) / 1000, c[1] - (y - o[1]) / 1000, c[2] + LAYOUT.pcb.size[2] + z);
}
