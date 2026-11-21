/* Bench Screen: draws the SOL-MIO v1.3 board from its Altium data and lights up where the next part goes.
   Classic script (no modules) so it also works from file://. Needs window.SOLMIO (solmio-board.js).
   Use:  const scr = BenchScreen.create(canvas); scr.set({ ref: 'D2', mode: 'place' }); then call scr.frame(seconds) every frame. */
(function () {
  // Edit values here if your BOM differs. Coordinates are board mm (Altium, y up).
  const TARGETS = [
    { ref: 'D2', cup: 'A1', name: 'Schottky diode', value: 'B5819WS · 1 A 40 V', pkg: 'SOD-323', at: [82.0, 90.9], a: 90, L: 1.7, W: 1.25,
      pads: [[82.0, 92.15], [82.0, 89.65]], mark: { pad: 1, text: 'BAND' }, tip: 'Band goes to the lower pad, toward the 7805.' },
    { ref: 'R1', cup: 'A2', name: 'Power-LED resistor', value: '', pkg: '0603', at: [87.6, 83.6], a: 0, L: 1.6, W: 0.8,
      pads: [[86.85, 83.6], [88.35, 83.6]], tip: 'No polarity.' },
    { ref: 'D1', cup: 'A3', name: 'Power LED', value: '', pkg: '1206', at: [93.1, 83.6], a: 0, L: 3.2, W: 1.6,
      pads: [[91.6, 83.6], [94.6, 83.6]], tip: 'Match the cathode mark to the silkscreen.' },
    { ref: 'C4', cup: 'B1', name: 'Electrolytic capacitor', value: '470 µF 25 V', pkg: 'V-chip 8 × 10', at: [74.7, 93.1], a: 90, L: 8.3, W: 8.3,
      pads: [[74.7, 96.5], [74.7, 89.7]], tip: 'The black stripe is minus. Match it to the silkscreen.' },
    { ref: 'C13', cup: 'B2', name: 'Electrolytic capacitor', value: '330 µF 25 V', pkg: 'V-chip 8 × 10', at: [55.8, 93.1], a: 90, L: 8.3, W: 8.3,
      pads: [[55.8, 96.5], [55.8, 89.7]], tip: 'The black stripe is minus. Match it to the silkscreen.' },
  ];
  const PREFIT = { U1: [[75.66, 81.3], [78.2, 81.3], [80.74, 81.3]] };
  const BYREF = Object.fromEntries(TARGETS.map((t) => [t.ref, t]));
  const C = {
    bg: '#0c1014', panel: '#111820', line: '#24313c', fg: '#e8edf1', muted: '#8a99a6',
    mask: '#ecede7', maskEdge: '#cfd2c7', silk: '#1f201d', pad: '#c3c7cb', hole: '#3c3d3a',
    hot: '#ffb547', ok: '#55c983', warn: '#ffb547', bad: '#f26b5e', led: '#58ff86',
  };
  const SANS = '"IBM Plex Sans", system-ui, -apple-system, "Segoe UI", sans-serif';
  const MONO = '"IBM Plex Mono", ui-monospace, Menlo, monospace';
  const rad = (d) => (d * Math.PI) / 180;

  function padsFor(p) {
    const P = [], add = (x, y, w, h, tht = false) => P.push({ x, y, w, h, tht });
    const L = p.L, W = p.W, t = BYREF[p.d];
    if (p.d === 'U1') { for (const x of [-2.54, 0, 2.54]) add(x, 0, 1.9, 2.4, true); return P; }
    if (p.d === 'J2') { add(0, 3.2, 3.2, 1.6, true); add(0, -2.8, 3.2, 1.6, true); add(-4.0, 0.2, 1.6, 3.2, true); return P; }
    if (t) {
      const a = -rad(t.a);
      for (const [x, y] of t.pads) { const dx = x - p.x, dy = y - p.y; add(dx * Math.cos(a) - dy * Math.sin(a), dx * Math.sin(a) + dy * Math.cos(a), p.k === 'cyl' ? 3.0 : L * 0.4, p.k === 'cyl' ? 2.0 : W * 1.05); }
      return P;
    }
    if (p.k === 'qfp') { for (let s = 0; s < 4; s++) for (let i = 0; i < 25; i++) { const q = -6 + i * 0.5, e = 7.6; const [x, y] = [[q, -e], [e, q], [-q, e], [-e, -q]][s]; add(x, y, s % 2 ? 1.4 : 0.28, s % 2 ? 0.28 : 1.4); } return P; }
    if (p.k === 'hdr') { const n = Math.round(L / 2.54); for (let i = 0; i < n; i++) add(-L / 2 + 1.27 + i * 2.54, 0, 1.7, 1.7, true); return P; }
    if (p.k === 'cyl') { add(-3.4, 0, 3.0, 2.0); add(3.4, 0, 3.0, 2.0); return P; }
    if (L === 7.4) { add(-1.25, -0.6, 1.8, 1.8, true); add(1.25, -0.6, 1.8, 1.8, true); return P; }
    if (p.d === 'P7') { for (const x of [-2.5, 0, 2.5]) add(x, -0.5, 1.8, 1.8, true); return P; }
    if (p.d === 'J8') { for (const x of [-2.54, 0, 2.54]) for (const y of [-1.27, 1.27]) add(x, y, 1.6, 1.6, true); return P; }
    if (p.d === 'J15') { for (let i = 0; i < 4; i++) add(-3 + i * 2, 0, 1.4, 1.4, true); return P; }
    if (p.d === 'Y1') { add(-2.44, 0, 1.6, 1.6, true); add(2.44, 0, 1.6, 1.6, true); return P; }
    if (p.d === 'U3') { for (let i = 0; i < 15; i++) add(-8.89 + i * 1.27, i % 2 ? 1.0 : -1.0, 1.1, 1.6, true); return P; }
    if (p.d === 'SW1') { for (const x of [-2.6, 2.6]) for (const y of [-1.3, 1.3]) add(x, y, 1.0, 0.9); return P; }
    if (p.d === 'D4') { for (const x of [-2.2, 2.2]) for (const y of [-1.6, 0, 1.6]) add(x, y, 1.1, 0.8); return P; }
    add(-L / 2 + L * 0.18, 0, L * 0.38, W * 1.05); add(L / 2 - L * 0.18, 0, L * 0.38, W * 1.05);
    return P;
  }

  function wrap(ctx, text, maxW) {
    const words = String(text).split(/\s+/), lines = [];
    let cur = '';
    for (const w of words) { const t = cur ? cur + ' ' + w : w; if (ctx.measureText(t).width > maxW && cur) { lines.push(cur); cur = w; } else cur = t; }
    if (cur) lines.push(cur);
    return lines;
  }
  // adds a rounded rectangle to the current path (no beginPath, so it can cut a hole in another shape)
  function rrect(ctx, x, y, w, h, r) { ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }

  function create(canvas, opts = {}) {
    const SOL = window.SOLMIO;
    const ctx = canvas.getContext('2d');
    const xs = SOL.outline.map((p) => p[0]), ys = SOL.outline.map((p) => p[1]);
    const B = { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) };
    let state = { ref: null, mode: 'idle', placed: [], flags: [], message: '' };
    const view = { cx: (B.x0 + B.x1) / 2, cy: (B.y0 + B.y1) / 2, s: 0 };
    let last = null;

    function layout() {
      const W = canvas.width, H = canvas.height, pw = Math.round(W * (opts.panelRatio || 0.36));
      return { W, H, bx: 0, by: 0, bw: W - pw, bh: H, px: W - pw, pw };
    }
    function goalView(Lo) {
      const t = BYREF[state.ref];
      const pad = 0.92;
      if (!t || state.mode === 'done' || state.mode === 'idle') {
        const s = Math.min(Lo.bw / (B.x1 - B.x0), Lo.bh / (B.y1 - B.y0)) * pad;
        return { cx: (B.x0 + B.x1) / 2, cy: (B.y0 + B.y1) / 2, s };
      }
      const win = Math.max(t.L, t.W) + 28; // mm of context around the part, enough to see its neighbours
      return { cx: t.at[0], cy: t.at[1], s: Math.min(Lo.bw, Lo.bh) / win };
    }

    function frame(now) {
      const Lo = layout();
      const dt = last == null ? 1 : Math.min(0.1, now - last); last = now;
      const g = goalView(Lo);
      if (!view.s) Object.assign(view, g);
      const k = opts.instant ? 1 : 1 - Math.exp(-dt * 4.5);
      // zoom in log space so it feels even
      view.cx += (g.cx - view.cx) * k; view.cy += (g.cy - view.cy) * k; view.s = Math.exp(Math.log(view.s) + (Math.log(g.s) - Math.log(view.s)) * k);
      const rot = state.rot180 ? -1 : 1;
      const X = (x) => Lo.bx + Lo.bw / 2 + rot * (x - view.cx) * view.s;
      const Y = (y) => Lo.by + Lo.bh / 2 - rot * (y - view.cy) * view.s;
      const pulse = 0.5 + 0.5 * Math.sin(now * 4.2);
      const H = Lo.H;

      ctx.save();
      ctx.fillStyle = C.bg; ctx.fillRect(0, 0, Lo.W, Lo.H);
      ctx.beginPath(); ctx.rect(Lo.bx, Lo.by, Lo.bw, Lo.bh); ctx.clip();

      // board
      ctx.beginPath(); SOL.outline.forEach(([x, y], i) => (i ? ctx.lineTo(X(x), Y(y)) : ctx.moveTo(X(x), Y(y)))); ctx.closePath();
      ctx.fillStyle = C.mask; ctx.fill(); ctx.lineWidth = Math.max(1, view.s * 0.3); ctx.strokeStyle = C.maskEdge; ctx.stroke();
      const onPart = (p, fn) => { ctx.save(); ctx.translate(X(p.x), Y(p.y)); ctx.rotate(-rad(p.a || 0) + (rot < 0 ? Math.PI : 0)); ctx.scale(view.s, -view.s); fn(); ctx.restore(); };
      for (const p of SOL.parts) onPart(p, () => {
        for (const q of padsFor(p)) {
          if (p.b && !q.tht) continue;
          ctx.fillStyle = C.pad;
          if (q.tht) { ctx.beginPath(); ctx.ellipse(q.x, q.y, q.w / 2, q.h / 2, 0, 0, 7); ctx.fill(); ctx.fillStyle = C.hole; ctx.beginPath(); ctx.arc(q.x, q.y, 0.45, 0, 7); ctx.fill(); }
          else ctx.fillRect(q.x - q.w / 2, q.y - q.h / 2, q.w, q.h);
        }
      });
      ctx.strokeStyle = C.silk; ctx.lineWidth = 0.16;
      for (const p of SOL.parts) if (!p.b) onPart(p, () => { ctx.strokeRect(-(p.L + 0.7) / 2, -(p.W + 0.7) / 2, p.L + 0.7, p.W + 0.7); if (p.d === 'D2') { ctx.fillStyle = C.silk; ctx.fillRect(-(p.L + 0.7) / 2, -(p.W + 0.7) / 2, 0.4, p.W + 0.7); } });
      for (const [x, y, d] of SOL.holes) { ctx.fillStyle = C.pad; ctx.beginPath(); ctx.arc(X(x), Y(y), (d / 2 + 0.9) * view.s, 0, 7); ctx.fill(); ctx.fillStyle = C.bg; ctx.beginPath(); ctx.arc(X(x), Y(y), (d / 2) * view.s, 0, 7); ctx.fill(); }
      // placed parts (simple bodies) and the pre-fitted regulator
      const body = (t, color) => onPart({ x: t.at[0], y: t.at[1], a: t.a }, () => { ctx.fillStyle = color; if (t.pkg && t.pkg.startsWith('V-chip')) { ctx.beginPath(); ctx.arc(0, 0, 4, 0, 7); ctx.fill(); } else ctx.fillRect(-t.L * 0.36, -t.W / 2, t.L * 0.72, t.W); });
      body({ at: [78.2, 81.3], a: 0, L: 10, W: 4.6 }, '#26282b');
      body({ at: [92.6, 93.5], a: 90, L: 14.4, W: 9 }, '#26282b');
      for (const r of state.placed || []) { const t = BYREF[r]; if (t) body(t, r === 'D1' && state.ledOn ? C.led : t.pkg.startsWith('V-chip') ? '#b9bfc5' : '#2b2d30'); }
      if (view.s > 3.2) {
        ctx.fillStyle = C.silk; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = `600 ${Math.max(8, Math.min(16, view.s * 1.15))}px ${MONO}`;
        for (const p of SOL.parts) if (!p.b) { const side = (Math.round(p.a || 0) % 180 === 90 ? p.L : p.W) / 2; ctx.fillText(p.d, X(p.x), Y(p.y + rot * (side + 1.3))); }
      }

      const t = BYREF[state.ref];
      const focus = t && state.mode !== 'done' && state.mode !== 'idle';
      if (focus) {
        // dim everything except the footprint
        const pad = 2.6, hw = (t.a % 180 === 90 ? t.W : t.L) / 2 + pad, hh = (t.a % 180 === 90 ? t.L : t.W) / 2 + pad;
        const fx0 = X(t.at[0] - hw), fx1 = X(t.at[0] + hw), fy0 = Y(t.at[1] + hh), fy1 = Y(t.at[1] - hh);
        const rx = Math.min(fx0, fx1), ry = Math.min(fy0, fy1), rw = Math.abs(fx1 - fx0), rh = Math.abs(fy1 - fy0);
        ctx.beginPath(); ctx.rect(Lo.bx, Lo.by, Lo.bw, Lo.bh); rrect(ctx, rx, ry, rw, rh, Math.min(rw, rh) * 0.18);
        ctx.fillStyle = 'rgba(5,8,11,0.68)'; ctx.fill('evenodd');
        // crosshair to help find it on the real board
        ctx.setLineDash([6, 6]); ctx.strokeStyle = 'rgba(255,181,71,0.35)'; ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(Lo.bx, Y(t.at[1])); ctx.lineTo(rx, Y(t.at[1])); ctx.moveTo(rx + rw, Y(t.at[1])); ctx.lineTo(Lo.bx + Lo.bw, Y(t.at[1]));
        ctx.moveTo(X(t.at[0]), Lo.by); ctx.lineTo(X(t.at[0]), ry); ctx.moveTo(X(t.at[0]), ry + rh); ctx.lineTo(X(t.at[0]), Lo.by + Lo.bh); ctx.stroke(); ctx.setLineDash([]);
        // glowing pads
        ctx.save(); ctx.shadowColor = C.hot; ctx.shadowBlur = 18 + 16 * pulse;
        const mode = state.mode;
        onPart({ x: t.at[0], y: t.at[1], a: t.a }, () => {
          ctx.strokeStyle = C.hot; ctx.lineWidth = 0.35; ctx.strokeRect(-(t.L + 1.2) / 2, -(t.W + 1.2) / 2, t.L + 1.2, t.W + 1.2);
        });
        for (const [x, y] of t.pads) {
          const s = view.s, w = (t.pkg.startsWith('V-chip') ? 3.0 : t.L * 0.4) * s, h = (t.pkg.startsWith('V-chip') ? 2.0 : t.W * 1.05) * s;
          const vertical = t.a % 180 === 90;
          ctx.fillStyle = `rgba(255,181,71,${mode === 'place' ? 0.55 + 0.45 * pulse : 0.35})`;
          ctx.fillRect(X(x) - (vertical ? h : w) / 2, Y(y) - (vertical ? w : h) / 2, vertical ? h : w, vertical ? w : h);
        }
        ctx.restore();
        // polarity mark
        if (t.mark) {
          const [x, y] = t.pads[t.mark.pad], px = X(x), py = Y(y), dir = Y(y) > Y(t.at[1]) ? 1 : -1;
          ctx.strokeStyle = C.fg; ctx.fillStyle = C.fg; ctx.lineWidth = 2;
          const tipY = py + dir * (1.4 * view.s), endY = tipY + dir * 0.09 * H;
          ctx.beginPath(); ctx.moveTo(px, endY); ctx.lineTo(px, tipY); ctx.stroke();
          ctx.beginPath(); ctx.moveTo(px, tipY); ctx.lineTo(px - 7, tipY + dir * 12); ctx.lineTo(px + 7, tipY + dir * 12); ctx.closePath(); ctx.fill();
          ctx.font = `600 ${Math.round(H * 0.032)}px ${MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = dir > 0 ? 'top' : 'bottom';
          ctx.fillText(t.mark.text, px, endY + dir * 6);
        }
        // ref callout
        ctx.font = `700 ${Math.round(H * 0.07)}px ${SANS}`; ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
        ctx.fillStyle = C.hot; ctx.fillText(t.ref, rx + rw + 14, ry - 6);
      }
      // joint flags (e.g. a cold joint found by the wrist camera)
      for (const f of state.flags || []) {
        const ft = BYREF[f.ref]; if (!ft) continue;
        const [x, y] = ft.pads[(f.pad || 1) - 1];
        const col = f.kind === 'ok' ? C.ok : f.kind === 'bad' ? C.bad : C.warn;
        ctx.save(); ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.shadowColor = col; ctx.shadowBlur = 12 + 12 * pulse;
        ctx.beginPath(); ctx.arc(X(x), Y(y), Math.max(10, 2.2 * view.s), 0, 7); ctx.stroke(); ctx.restore();
        ctx.font = `600 ${Math.round(H * 0.03)}px ${MONO}`; ctx.fillStyle = col; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
        ctx.fillText(f.text || f.kind, X(x) + Math.max(14, 2.6 * view.s), Y(y));
      }
      if (state.mode === 'done' && state.ledOn) {
        const d1 = BYREF.D1; ctx.save(); ctx.shadowColor = C.led; ctx.shadowBlur = 30 + 20 * pulse; ctx.fillStyle = C.led;
        ctx.beginPath(); ctx.arc(X(d1.at[0]), Y(d1.at[1]), Math.max(5, 1.6 * view.s), 0, 7); ctx.fill(); ctx.restore();
      }
      // minimap while zoomed in
      if (focus) {
        const mw = Lo.bw * 0.22, ms = mw / (B.x1 - B.x0), mh = (B.y1 - B.y0) * ms, mx = Lo.bx + 14, my = Lo.by + Lo.bh - mh - 14;
        const MX = (x) => mx + (rot > 0 ? x - B.x0 : B.x1 - x) * ms, MY = (y) => my + (rot > 0 ? B.y1 - y : y - B.y0) * ms;
        ctx.globalAlpha = 0.92; ctx.beginPath(); SOL.outline.forEach(([x, y], i) => (i ? ctx.lineTo(MX(x), MY(y)) : ctx.moveTo(MX(x), MY(y)))); ctx.closePath();
        ctx.fillStyle = '#cfd2c7'; ctx.fill(); ctx.globalAlpha = 1;
        ctx.fillStyle = C.hot; ctx.beginPath(); ctx.arc(MX(t.at[0]), MY(t.at[1]), 5, 0, 7); ctx.fill();
      }
      ctx.restore();

      // ---------------- side panel
      const px = Lo.px, pw = Lo.pw, m = Math.round(pw * 0.08);
      ctx.fillStyle = C.panel; ctx.fillRect(px, 0, pw, H);
      ctx.fillStyle = C.line; ctx.fillRect(px, 0, 2, H);
      let y = m;
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      ctx.fillStyle = C.muted; ctx.font = `600 ${Math.round(H * 0.026)}px ${MONO}`;
      ctx.fillText('SOL-MIO v1.3 · POWER STAGE', px + m, y); y += H * 0.05;
      // step dots
      const idx = TARGETS.findIndex((q) => q.ref === state.ref), dot = H * 0.014;
      TARGETS.forEach((q, i) => {
        const cx = px + m + dot + i * dot * 3.2, cy = y + dot;
        ctx.beginPath(); ctx.arc(cx, cy, dot, 0, 7);
        if ((state.placed || []).includes(q.ref)) { ctx.fillStyle = C.ok; ctx.fill(); }
        else if (i === idx && focus) { ctx.fillStyle = C.hot; ctx.fill(); }
        else { ctx.strokeStyle = C.muted; ctx.lineWidth = 2; ctx.stroke(); }
      });
      y += dot * 2 + H * 0.045;
      if (focus) {
        ctx.fillStyle = C.muted; ctx.font = `500 ${Math.round(H * 0.03)}px ${MONO}`;
        ctx.fillText(`STEP ${idx + 1} / ${TARGETS.length}`, px + m, y); y += H * 0.045;
        ctx.fillStyle = C.fg; ctx.font = `700 ${Math.round(H * 0.15)}px ${SANS}`; ctx.fillText(t.ref, px + m - 4, y); y += H * 0.165;
        ctx.font = `600 ${Math.round(H * 0.045)}px ${SANS}`;
        for (const ln of wrap(ctx, t.name, pw - 2 * m)) { ctx.fillText(ln, px + m, y); y += H * 0.055; }
        ctx.fillStyle = C.muted; ctx.font = `500 ${Math.round(H * 0.032)}px ${MONO}`;
        for (const ln of [t.value, t.pkg].filter(Boolean)) { ctx.fillText(ln, px + m, y); y += H * 0.042; }
        y += H * 0.02;
        // cup badge
        const bh = H * 0.075, label = `CUP ${t.cup}`;
        ctx.font = `700 ${Math.round(H * 0.042)}px ${MONO}`;
        const bw = ctx.measureText(label).width + H * 0.05;
        ctx.beginPath(); rrect(ctx, px + m, y, bw, bh, 8); ctx.fillStyle = C.hot; ctx.fill();
        ctx.fillStyle = '#1b1206'; ctx.textBaseline = 'middle'; ctx.fillText(label, px + m + H * 0.025, y + bh / 2); ctx.textBaseline = 'top';
        y += bh + H * 0.04;
        ctx.fillStyle = C.fg; ctx.font = `500 ${Math.round(H * 0.036)}px ${SANS}`;
        for (const ln of wrap(ctx, state.tip || t.tip, pw - 2 * m)) { ctx.fillText(ln, px + m, y); y += H * 0.048; }
      } else if (state.mode === 'done') {
        ctx.fillStyle = C.ok; ctx.font = `700 ${Math.round(H * 0.07)}px ${SANS}`;
        for (const ln of wrap(ctx, 'Power stage done', pw - 2 * m)) { ctx.fillText(ln, px + m, y); y += H * 0.08; }
        ctx.fillStyle = C.fg; ctx.font = `500 ${Math.round(H * 0.036)}px ${SANS}`;
        for (const ln of wrap(ctx, state.ledOn ? '12 V in, 5 V out, D1 is on.' : 'All joints checked. Plug in 12 V.', pw - 2 * m)) { ctx.fillText(ln, px + m, y); y += H * 0.048; }
      } else {
        ctx.fillStyle = C.fg; ctx.font = `600 ${Math.round(H * 0.05)}px ${SANS}`;
        ctx.fillText(state.mode === 'inspect' ? 'Checking joints' : 'Waiting for Claude', px + m, y);
      }
      // status pill + caption at the bottom
      const modeText = { place: 'PLACE AND SOLDER', inspect: 'INSPECTING', reheat: 'REHEAT', ok: 'CHECKED', done: 'DONE', idle: 'IDLE' }[state.mode] || String(state.mode).toUpperCase();
      const modeCol = { place: C.hot, inspect: C.muted, reheat: C.warn, ok: C.ok, done: C.ok }[state.mode] || C.muted;
      ctx.font = `600 ${Math.round(H * 0.03)}px ${MONO}`;
      const tw = ctx.measureText(modeText).width + H * 0.04, ph = H * 0.058, py0 = H - m - ph;
      ctx.beginPath(); rrect(ctx, px + m, py0, tw, ph, ph / 2); ctx.strokeStyle = modeCol; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = modeCol; ctx.textBaseline = 'middle'; ctx.fillText(modeText, px + m + H * 0.02, py0 + ph / 2);
      if (state.message) {
        ctx.fillStyle = C.muted; ctx.font = `italic 400 ${Math.round(H * 0.028)}px ${SANS}`; ctx.textBaseline = 'bottom';
        const lines = wrap(ctx, '“' + state.message + '”', pw - 2 * m).slice(0, 3);
        lines.reverse().forEach((ln, i) => ctx.fillText(ln, px + m, py0 - H * 0.02 - i * H * 0.036));
      }
    }

    return {
      set(s) { state = Object.assign({ placed: [], flags: [] }, s); },
      get state() { return state; },
      frame,
    };
  }

  window.BenchScreen = { create, TARGETS };
})();
