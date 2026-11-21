// Node example: plan and simulate a character, print a few joint angles.   node js/example.mjs trickster kick_ball
import { readFileSync } from 'node:fs';
import { plan, perform } from './thc.js';

const data = JSON.parse(readFileSync(new URL('../characters.json', import.meta.url)));
const [name = 'trickster', move = 'kick_ball'] = process.argv.slice(2);
const keyframes = data.engine.gestures[move];
const steps = plan(data.engine, data.characters[name], keyframes);
const frames = perform(data, name, keyframes);
console.log(`${name} / ${move}: ${steps.length} steps, ${(frames.length / data.fps).toFixed(1)} s of motion`);
for (let f = 0; f < frames.length; f += 15) console.log(`t=${(f / data.fps).toFixed(2)}s`, frames[f].map((x) => x.toFixed(3)).join(' '));
