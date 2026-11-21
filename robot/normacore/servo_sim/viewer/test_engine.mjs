// Check the browser engine against the MuJoCo physics clips: same plan, same timing, similar motion.
//   node test_engine.mjs            (from servo_sim/viewer)
import { readFileSync } from 'node:fs';
import { perform, simulate, plan } from './engine.js';

const data = JSON.parse(readFileSync(new URL('./anim.json', import.meta.url)));
const E = data.engine;
const gestures = Object.entries(E.gestures);
const deg = (r) => (r * 180) / Math.PI;

function compare(tau) {
  let sum = 0, n = 0, worst = 0, durErr = 0, clips = 0;
  for (const name of Object.keys(data.characters)) {
    for (const [g, kfs] of gestures) {
      const phys = data.clips[`${name}/${g}`].q;
      const mine = simulate(E, plan(E, data.characters[name], kfs), data.stand, data.fps, tau);
      const L = Math.min(phys.length, mine.length);
      for (let f = 0; f < L; f++) for (let i = 0; i < 7; i++) {       // j8 jaws: tiny inertia, skip
        const e = Math.abs(phys[f][i] - mine[f][i]); sum += e; n++; worst = Math.max(worst, e);
      }
      durErr += Math.abs(phys.length - mine.length) / data.fps; clips++;
    }
  }
  return { tau, meanDeg: deg(sum / n), worstDeg: deg(worst), meanDurDiff: durErr / clips };
}

if (process.argv.includes('--fit')) {
  for (const tau of [0.005, 0.01, 0.015, 0.02]) console.log(compare(tau));
} else {
  const r = compare(undefined);
  console.log(`mean joint difference ${r.meanDeg.toFixed(2)}°, worst ${r.worstDeg.toFixed(1)}°, clip length differs by ${r.meanDurDiff.toFixed(2)} s on average`);
  // a prompt-style choreography runs for every character
  const kf = [[1, { j6: -1, j8: 2 }], [0.5, { j8: 0 }], [1, { j1: 1.5 }], [1, { j1: -1.5 }], [1.5, { j1: 0, j6: 0 }]];
  for (const name of Object.keys(data.characters)) {
    const frames = perform(data, name, kf);
    if (!frames.length || frames.some((q) => q.some((x) => !Number.isFinite(x)))) throw new Error('bad frames for ' + name);
  }
  console.log('custom choreography performs for all', Object.keys(data.characters).length, 'characters');
}
