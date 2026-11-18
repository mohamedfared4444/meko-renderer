/* VE2 engine-world.js — builds the deterministic SVG world ONCE at init.
   Layers: bg > belt-back > machines-back > products-back > products > machines-front > effects > labels
   All geometry in world coordinates. No randomness at render time (seeded offsets baked at init). */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const G = {
    BELT_Y: 640, BELT_BOT: 676, FLOOR: 800,
    ROASTER: { x0: 620, x1: 1080, y0: 400, y1: 780, drumC: [850, 545], drumR: 112, winR: 100, chim: [930, 985, 240, 400], entry: [620, 640, 596, 676], exit: [1060, 1080, 596, 676], banner: [850, 318] },
    GRINDER: { x0: 1300, x1: 1740, y0: 380, y1: 780, r1: [1455, 520, 80], r2: [1585, 520, 80], win: [1400, 1640, 430, 640], hop: [1370, 1670, 300, 390], entry: [1300, 1320, 596, 676], exit: [1720, 1740, 596, 676], banner: [1520, 268] },
    TANK: { x0: 1960, x1: 2400, y0: 430, y1: 780, win: [2000, 2360, 500, 640], pool: [2006, 2354, 540, 640], agit: 2180, outlet: [2388, 2412, 495, 515], entry: [1960, 1980, 596, 676], banner: [2180, 352] },
    PIPE: { cx1: 2400, cx2: 2700, yTop: 430, yStart: 505, yEnd: 360 },
    FUNNEL: { x0: 2600, x1: 2800, y0: 350, y1: 800, spout: [2680, 2720, 500, 545], win: [2652, 2748, 470, 648], banner: [2700, 262] },
    TUNNEL: { x0: 3080, x1: 3560, y0: 380, y1: 780, entry: [3080, 3100, 556, 676], exit: [3540, 3560, 556, 676], win: [3150, 3490, 425, 545], banner: [3320, 262] },
    STATION: { gantryArmY: 330, colX: [4290, 4330], arm: [3660, 4330], clawHomeY: 360, liftY: 494, moldStop: 3670, beltEnd: [3840, 3872], shelf: [3872, 4380] },
    MOLD: { w: 150, hTop: 556, hBot: 640, barTop: 584, wall: 12, spawnL: 2605, stopL: 2625, exitX: 2800, tEntry: 3080, tExit: 3560 },
    SPEED: 200
  };
  const C = {
    gold: '#FFC94D', cream: '#F5EDE0', sub: '#d8c8b8',
    liquid: '#6b4226', liquidHi: '#8a5a33', paste: '#4e3320', barDark: '#492a15',
    beanRaw: '#4a2f1d', beanRoast: '#6b4423',
    shell: '#3a2c20', shellIn: '#1f150d'
  };

  const V = { G, C, els: {}, machines: [] };
  window.VE2 = V;

  function el(tag, attrs, parent, text) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (text !== undefined) e.textContent = text;
    (parent || V.els.worldRoot).appendChild(e);
    return e;
  }
  V.el = el;

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  V.mulberry32 = mulberry32;

  function rect(x, y, w, h) { return { x, y, w, h }; }
  function machineBox(id, x0, x1, y0, y1) { V.machines.push({ id, x0, x1, y0, y1 }); }

  /* ================= LAYER: BG ================= */
  function buildBG() {
    const L = V.els['layer-bg'];
    el('rect', { x: -300, y: -2400, width: 5200, height: 3200, fill: 'url(#gWall)' }, L);
    // wall panel seams
    for (let x = -300; x <= 4900; x += 300) {
      el('rect', { x: x - 3, y: -400, width: 6, height: 1180, fill: '#241826', opacity: 0.55 }, L);
    }
    el('rect', { x: -300, y: 208, width: 5200, height: 14, fill: '#2c1f30', opacity: 0.8 }, L);
    // lamps + glow
    for (let x = 60; x <= 4700; x += 640) {
      el('rect', { x: x - 46, y: 96, width: 92, height: 18, rx: 6, fill: '#3a2c3a' }, L);
      el('ellipse', { cx: x, cy: 128, rx: 190, ry: 150, fill: 'url(#gLamp)' }, L);
      el('rect', { x: x - 34, y: 112, width: 68, height: 7, rx: 3, fill: '#ffd98a', opacity: 0.85 }, L);
    }
    // floor
    el('rect', { x: -300, y: G.FLOOR, width: 5200, height: 3800, fill: 'url(#gFloor)' }, L);
    el('rect', { x: -300, y: G.FLOOR, width: 5200, height: 8, fill: '#3a2c40', opacity: 0.9 }, L);
    // subtle floor seams
    for (let x = -240; x <= 4900; x += 260) {
      el('rect', { x, y: G.FLOOR + 40, width: 4, height: 220, fill: '#1c1420', opacity: 0.5 }, L);
    }
  }

  /* ================= LAYER: BELT-BACK ================= */
  function buildBelt() {
    const L = V.els['layer-belt-back'];
    const y = G.BELT_Y;
    el('rect', { x: -300, y: y, width: 4700, height: G.BELT_BOT - y, fill: 'url(#gBelt)' }, L);
    const top = el('rect', { x: -300, y: y, width: 4700, height: 6, fill: '#4a4356' }, L);
    const dash = el('line', { x1: -300, y1: y + 3, x2: 4400, y2: y + 3, stroke: '#5c5468', 'stroke-width': 3, 'stroke-dasharray': '34 30' }, L);
    V.els.beltDash = dash;
    V.els.beltTop = top;
    // rollers
    const rollers = [];
    for (let x = -260; x <= 4380; x += 88) {
      const c = el('circle', { cx: x, cy: (y + G.BELT_BOT) / 2 + 8, r: 11, fill: '#3c3546', stroke: '#524a5e', 'stroke-width': 2 }, L);
      el('line', { x1: x - 7, y1: (y + G.BELT_BOT) / 2 + 8, x2: x + 7, y2: (y + G.BELT_BOT) / 2 + 8, stroke: '#5c5468', 'stroke-width': 2 }, c);
      rollers.push(c);
    }
    V.els.rollers = rollers;
    // supports
    for (let x = -180; x <= 4300; x += 480) {
      el('rect', { x, y: G.BELT_BOT, width: 16, height: G.FLOOR - G.BELT_BOT, fill: '#2c2434' }, L);
      el('rect', { x: x - 12, y: G.FLOOR - 10, width: 40, height: 10, fill: '#241d2c' }, L);
    }
  }

  /* ================= ROASTER ================= */
  function buildRoaster() {
    const R = G.ROASTER;
    const back = V.els['layer-machines-back'], front = V.els['layer-machines-front'];
    // chimney (behind body)
    el('rect', { x: R.chim[0], y: R.chim[2], width: R.chim[1] - R.chim[0], height: R.y0 - R.chim[2], fill: '#5f3a1c' }, back);
    el('rect', { x: R.chim[0] - 8, y: R.chim[2], width: R.chim[1] - R.chim[0] + 16, height: 16, rx: 4, fill: '#6d4423' }, back);
    // drum (seen through cutaway window)
    const [cx, cy] = R.drumC;
    el('circle', { cx, cy, r: R.drumR, fill: '#2a180c', stroke: '#1f1007', 'stroke-width': 6 }, back);
    const drum = el('g', {}, back);
    const drumRot = el('g', {}, drum);
    for (let i = 0; i < 6; i++) {
      const a = i * 60;
      el('line', { x1: cx, y1: cy, x2: cx + Math.cos(a * Math.PI / 180) * (R.drumR - 16), y2: cy + Math.sin(a * Math.PI / 180) * (R.drumR - 16), stroke: '#7c4c24', 'stroke-width': 7, 'stroke-linecap': 'round', opacity: 0.85 }, drumRot);
      el('circle', { cx: cx + Math.cos(a * Math.PI / 180) * (R.drumR - 22), cy: cy + Math.sin(a * Math.PI / 180) * (R.drumR - 22), r: 7, fill: '#96602f' }, drumRot);
    }
    el('circle', { cx, cy, r: 16, fill: '#5f3a1c', stroke: '#96602f', 'stroke-width': 4 }, drum);
    V.els.drumRot = drumRot;
    // drum beans (in products-back, visible through window)
    const pb = V.els['layer-products-back'];
    const drumBeans = el('g', {}, pb);
    const rnd = mulberry32(101);
    const db = [];
    for (let i = 0; i < 9; i++) {
      const rad = 34 + rnd() * 58, base = rnd() * 360, sp = 1.25 + rnd() * 0.5;
      const b = el('ellipse', { cx: 0, cy: 0, rx: 12, ry: 8.5, fill: C.beanRoast }, drumBeans);
      db.push({ rad, base, sp, b });
    }
    V.els.drumBeans = db;
    // front face with holes (evenodd): body + drum window + entry + exit
    const d = `M ${R.x0} ${R.y0} H ${R.x1} V ${R.y1} H ${R.x0} Z
      M ${cx - R.winR} ${cy} a ${R.winR} ${R.winR} 0 1 0 ${2 * R.winR} 0 a ${R.winR} ${R.winR} 0 1 0 ${-2 * R.winR} 0 Z
      M ${R.entry[0]} ${R.entry[2]} H ${R.entry[1]} V ${R.entry[3]} H ${R.entry[0]} Z
      M ${R.exit[0]} ${R.exit[2]} H ${R.exit[1]} V ${R.exit[3]} H ${R.exit[0]} Z`;
    el('path', { d, 'fill-rule': 'evenodd', fill: 'url(#gCopper)', stroke: '#4a2c12', 'stroke-width': 5 }, front);
    el('circle', { cx, cy, r: R.winR, fill: 'none', stroke: '#3a2410', 'stroke-width': 9 }, front);
    el('circle', { cx, cy, r: R.winR + 5, fill: 'none', stroke: '#96602f', 'stroke-width': 3, opacity: 0.7 }, front);
    // hole rims
    el('rect', { x: R.entry[0] - 4, y: R.entry[2] - 4, width: R.entry[1] - R.entry[0] + 8, height: R.entry[3] - R.entry[2] + 8, fill: 'none', stroke: '#4a2c12', 'stroke-width': 4 }, front);
    el('rect', { x: R.exit[0] - 4, y: R.exit[2] - 4, width: R.exit[1] - R.exit[0] + 8, height: R.exit[3] - R.exit[2] + 8, fill: 'none', stroke: '#4a2c12', 'stroke-width': 4 }, front);
    // legs + base plate
    el('rect', { x: R.x0 + 30, y: R.y1 - 6, width: 22, height: G.FLOOR - R.y1 + 6, fill: '#3a2410' }, front);
    el('rect', { x: R.x1 - 52, y: R.y1 - 6, width: 22, height: G.FLOOR - R.y1 + 6, fill: '#3a2410' }, front);
    // control panel
    el('rect', { x: R.x0 + 18, y: R.y0 + 22, width: 74, height: 44, rx: 8, fill: '#3a2410' }, front);
    el('circle', { cx: R.x0 + 40, cy: R.y0 + 44, r: 9, fill: C.gold, opacity: 0.9 }, front);
    el('circle', { cx: R.x0 + 68, cy: R.y0 + 44, r: 9, fill: '#c96a3a', opacity: 0.9 }, front);
    machineBox('roaster', R.x0, R.x1, R.chim[2], R.y1);
  }

  /* ================= GRINDER ================= */
  function buildGrinder() {
    const R = G.GRINDER;
    const back = V.els['layer-machines-back'], front = V.els['layer-machines-front'], pb = V.els['layer-products-back'];
    // hopper behind top
    el('path', { d: `M ${R.hop[0]} ${R.hop[2]} H ${R.hop[1]} L ${R.hop[1] - 30} ${R.hop[3]} H ${R.hop[0] + 30} Z`, fill: '#39414c', stroke: '#2c343e', 'stroke-width': 4 }, back);
    // rollers
    const rollers = [];
    [[R.r1, 1], [R.r2, -1]].forEach(([rr]) => {
      const g = el('g', {}, back);
      const c = el('circle', { cx: rr[0], cy: rr[1], r: rr[2], fill: 'url(#gSteel)', stroke: '#2c343e', 'stroke-width': 5 }, g);
      for (let i = 0; i < 4; i++) {
        const a = i * 45;
        el('line', { x1: rr[0] - Math.cos(a * Math.PI / 180) * (rr[2] - 10), y1: rr[1] - Math.sin(a * Math.PI / 180) * (rr[2] - 10), x2: rr[0] + Math.cos(a * Math.PI / 180) * (rr[2] - 10), y2: rr[1] + Math.sin(a * Math.PI / 180) * (rr[2] - 10), stroke: '#39414c', 'stroke-width': 4 }, g);
      }
      el('circle', { cx: rr[0], cy: rr[1], r: 10, fill: '#2c343e' }, g);
      rollers.push(g);
    });
    V.els.grindRollers = rollers;
    // grounds particles (falling between rollers)
    const parts = [];
    const rnd = mulberry32(202);
    for (let i = 0; i < 8; i++) {
      const ox = (rnd() - 0.5) * 56, ph = rnd() * 130, sz = 3 + rnd() * 3;
      const p = el('circle', { cx: 0, cy: 0, r: sz, fill: C.paste }, pb);
      parts.push({ ox, ph, p });
    }
    V.els.grindParts = parts;
    // trough + paste level
    el('rect', { x: 1452, y: 596, width: 136, height: 44, fill: '#232a33' }, pb);
    const pasteLvl = el('rect', { x: 1456, y: 640, width: 128, height: 0, fill: C.paste }, pb);
    V.els.pasteLvl = pasteLvl;
    // front face (evenodd): body + window + entry + exit
    const W = R.win;
    const d = `M ${R.x0} ${R.y0} H ${R.x1} V ${R.y1} H ${R.x0} Z
      M ${W[0]} ${W[2]} H ${W[1]} V ${W[3]} H ${W[0]} Z
      M ${R.entry[0]} ${R.entry[2]} H ${R.entry[1]} V ${R.entry[3]} H ${R.entry[0]} Z
      M ${R.exit[0]} ${R.exit[2]} H ${R.exit[1]} V ${R.exit[3]} H ${R.exit[0]} Z`;
    el('path', { d, 'fill-rule': 'evenodd', fill: 'url(#gSteel)', stroke: '#2c343e', 'stroke-width': 5 }, front);
    el('rect', { x: W[0], y: W[2], width: W[1] - W[0], height: W[3] - W[2], fill: 'none', stroke: '#2c343e', 'stroke-width': 8 }, front);
    el('rect', { x: R.entry[0] - 4, y: R.entry[2] - 4, width: R.entry[1] - R.entry[0] + 8, height: R.entry[3] - R.entry[2] + 8, fill: 'none', stroke: '#2c343e', 'stroke-width': 4 }, front);
    el('rect', { x: R.exit[0] - 4, y: R.exit[2] - 4, width: R.exit[1] - R.exit[0] + 8, height: R.exit[3] - R.exit[2] + 8, fill: 'none', stroke: '#2c343e', 'stroke-width': 4 }, front);
    el('rect', { x: R.x0 + 20, y: R.y0 + 18, width: 64, height: 38, rx: 7, fill: '#2c343e' }, front);
    el('circle', { cx: R.x0 + 52, cy: R.y0 + 37, r: 8, fill: C.gold, opacity: 0.85 }, front);
    el('rect', { x: R.x0 + 30, y: R.y1 - 6, width: 20, height: G.FLOOR - R.y1 + 6, fill: '#232a33' }, front);
    el('rect', { x: R.x1 - 50, y: R.y1 - 6, width: 20, height: G.FLOOR - R.y1 + 6, fill: '#232a33' }, front);
    machineBox('grinder', R.x0, R.x1, R.hop[2], R.y1);
  }

  /* ================= CONCHING TANK ================= */
  function buildTank() {
    const R = G.TANK;
    const back = V.els['layer-machines-back'], front = V.els['layer-machines-front'], pb = V.els['layer-products-back'];
    el('rect', { x: R.x0, y: R.y0, width: R.x1 - R.x0, height: R.y1 - R.y0, fill: '#2b4a58' }, back);
    // pool (through window)
    const P = R.pool;
    el('rect', { x: P[0], y: P[2], width: P[1] - P[0], height: P[3] - P[2], fill: '#1c2f38' }, pb);
    const lvlPaste = el('rect', { x: P[0], y: P[3], width: P[1] - P[0], height: 0, fill: C.paste }, pb);
    const lvlLiq = el('rect', { x: P[0], y: P[3], width: P[1] - P[0], height: 0, fill: 'url(#gLiquid)' }, pb);
    const surf = el('rect', { x: P[0], y: P[3], width: P[1] - P[0], height: 5, fill: C.liquidHi, opacity: 0.8 }, pb);
    const swirl = el('ellipse', { cx: 2180, cy: 600, rx: 120, ry: 16, fill: C.liquidHi, opacity: 0.2 }, pb);
    V.els.tankLvlPaste = lvlPaste; V.els.tankLvlLiq = lvlLiq; V.els.tankSurf = surf; V.els.tankSwirl = swirl;
    // agitator
    const ag = el('g', {}, pb);
    el('rect', { x: R.agit - 9, y: 462, width: 18, height: 100, rx: 6, fill: '#55606e' }, ag);
    const armG = el('g', {}, ag);
    el('line', { x1: R.agit, y1: 566, x2: R.agit + 128, y2: 566, stroke: '#55606e', 'stroke-width': 12, 'stroke-linecap': 'round' }, armG);
    el('line', { x1: R.agit, y1: 566, x2: R.agit - 128, y2: 566, stroke: '#55606e', 'stroke-width': 12, 'stroke-linecap': 'round' }, armG);
    el('circle', { cx: R.agit, cy: 566, r: 14, fill: '#39414c', stroke: '#55606e', 'stroke-width': 4 }, ag);
    V.els.agitArm = armG;
    // front face (evenodd): body + window + entry
    const W = R.win;
    const d = `M ${R.x0} ${R.y0} H ${R.x1} V ${R.y1} H ${R.x0} Z
      M ${W[0]} ${W[2]} H ${W[1]} V ${W[3]} H ${W[0]} Z
      M ${R.entry[0]} ${R.entry[2]} H ${R.entry[1]} V ${R.entry[3]} H ${R.entry[0]} Z`;
    el('path', { d, 'fill-rule': 'evenodd', fill: '#3a6b7d', stroke: '#27505e', 'stroke-width': 5 }, front);
    el('rect', { x: W[0], y: W[2], width: W[1] - W[0], height: W[3] - W[2], fill: 'none', stroke: '#27505e', 'stroke-width': 8 }, front);
    el('rect', { x: R.entry[0] - 4, y: R.entry[2] - 4, width: R.entry[1] - R.entry[0] + 8, height: R.entry[3] - R.entry[2] + 8, fill: 'none', stroke: '#27505e', 'stroke-width': 4 }, front);
    // outlet stub on right wall (pipe start)
    el('rect', { x: R.outlet[0] - 10, y: R.outlet[2] - 12, width: (R.outlet[1] - R.outlet[0]) + 20, height: (R.outlet[3] - R.outlet[2]) + 24, rx: 5, fill: '#39414c' }, front);
    el('rect', { x: R.x0 + 18, y: R.y0 + 18, width: 62, height: 36, rx: 7, fill: '#27505e' }, front);
    el('circle', { cx: R.x0 + 49, cy: R.y0 + 36, r: 8, fill: C.gold, opacity: 0.85 }, front);
    el('rect', { x: R.x0 + 30, y: R.y1 - 6, width: 20, height: G.FLOOR - R.y1 + 6, fill: '#27505e' }, front);
    el('rect', { x: R.x1 - 50, y: R.y1 - 6, width: 20, height: G.FLOOR - R.y1 + 6, fill: '#27505e' }, front);
    machineBox('tank', R.x0, R.x1, R.y0, R.y1);
  }

  /* ================= PIPE (closed, with viewing strip) ================= */
  function buildPipe() {
    const P = G.PIPE, back = V.els['layer-machines-back'], front = V.els['layer-machines-front'], pb = V.els['layer-products-back'];
    const path = `M ${P.cx1} ${P.yStart} L ${P.cx1} ${P.yTop} L ${P.cx2} ${P.yTop} L ${P.cx2} ${P.yEnd}`;
    // interior clip rects (union) — liquid may ONLY exist inside these (Fix 2)
    const ic = document.getElementById('pipeInteriorRect');
    const frags = [
      [P.cx1 - 8, P.yTop - 8, 16, P.yStart - P.yTop + 8],
      [P.cx1 - 8, P.yTop - 8, (P.cx2 - P.cx1) + 16, 16],
      [P.cx2 - 8, P.yEnd - 8, 16, (P.yTop - P.yEnd) + 8]
    ];
    ic.setAttribute('x', P.cx1 - 8); ic.setAttribute('y', P.yTop - 8);
    // multiple rects in one clipPath: add siblings
    const clip = ic.parentNode;
    frags.forEach(f => {
      const r = document.createElementNS(NS, 'rect');
      r.setAttribute('x', f[0]); r.setAttribute('y', f[1]); r.setAttribute('width', f[2]); r.setAttribute('height', f[3]);
      clip.appendChild(r);
    });
    ic.remove(); // first placeholder replaced by frags
    // dark bore (back wall of pipe)
    el('path', { d: path, fill: 'none', stroke: '#17121c', 'stroke-width': 30, 'stroke-linejoin': 'round', 'stroke-linecap': 'butt' }, back);
    el('path', { d: path, fill: 'none', stroke: '#2c2434', 'stroke-width': 24, 'stroke-linejoin': 'round' }, back);
    // liquid stream (clipped to interior)
    const liqG = el('g', { 'clip-path': 'url(#pipeInteriorClip)' }, pb);
    const liq = el('path', { id: 'pipeLiquid', d: `M ${P.cx1} ${P.yStart - 2} L ${P.cx1} ${P.yTop} L ${P.cx2} ${P.yTop} L ${P.cx2} ${P.yEnd - 4}`, fill: 'none', stroke: 'url(#gLiquid)', 'stroke-width': 11, 'stroke-dasharray': '26 18' }, liqG);
    const liqHi = el('path', { id: 'pipeLiquidHi', d: `M ${P.cx1 - 2} ${P.yStart - 2} L ${P.cx1 - 2} ${P.yTop} L ${P.cx2 - 2} ${P.yTop} L ${P.cx2 - 2} ${P.yEnd - 4}`, fill: 'none', stroke: C.liquidHi, 'stroke-width': 3, 'stroke-dasharray': '18 26', opacity: 0.75 }, liqG);
    V.els.pipeLiq = liq; V.els.pipeLiqHi = liqHi;
    // front rails (viewing strip): outer side + inner side
    el('path', { d: `M ${P.cx1 + 15} ${P.yStart} L ${P.cx1 + 15} ${P.yTop - 15} L ${P.cx2 + 15} ${P.yTop - 15} L ${P.cx2 + 15} ${P.yEnd}`, fill: 'none', stroke: '#55606e', 'stroke-width': 9, 'stroke-linejoin': 'round' }, front);
    el('path', { d: `M ${P.cx1 - 15} ${P.yStart} L ${P.cx1 - 15} ${P.yTop + 15} L ${P.cx2 - 15} ${P.yTop + 15} L ${P.cx2 - 15} ${P.yEnd}`, fill: 'none', stroke: '#49525e', 'stroke-width': 9, 'stroke-linejoin': 'round' }, front);
    // flanges
    el('rect', { x: P.cx1 - 17, y: P.yStart - 12, width: 34, height: 14, rx: 3, fill: '#39414c' }, front);
    el('rect', { x: P.cx2 - 17, y: P.yEnd - 14, width: 34, height: 14, rx: 3, fill: '#39414c' }, front);
    el('rect', { x: P.cx1 - 20, y: P.yTop - 20, width: 40, height: 40, rx: 6, fill: '#414a56', stroke: '#2c343e', 'stroke-width': 3 }, front);
    machineBox('pipe', P.cx1 - 20, P.cx2 + 20, P.yEnd - 14, P.yStart);
  }

  /* ================= FUNNEL (depositor cabinet w/ integrated mold magazine) ================= */
  function buildFunnel() {
    const R = G.FUNNEL;
    const back = V.els['layer-machines-back'], front = V.els['layer-machines-front'], pb = V.els['layer-products-back'];
    // hopper liquid (behind, visible through window)
    const lw = el('g', {}, pb);
    const funLvl = el('rect', { x: 2664, y: R.spout[2], width: 72, height: 0, fill: 'url(#gLiquid)' }, lw);
    const funSurf = el('rect', { x: 2664, y: R.spout[2], width: 72, height: 5, fill: C.liquidHi, opacity: 0.8 }, lw);
    V.els.funLvl = funLvl; V.els.funSurf = funSurf;
    // cabinet front (evenodd): hopper trapezoid + base + window hole
    const W = R.win, S = R.spout;
    const d = `M ${R.x0} ${R.y0} H ${R.x1} L ${S[1]} ${S[2]} L ${S[1]} ${S[2] + 14} H ${R.x1} V ${R.y1} H ${R.x0} V ${S[2] + 14} H ${S[0]} L ${S[0]} ${S[2]} Z
      M ${W[0]} ${W[2]} H ${W[1]} V ${W[3]} H ${W[0]} Z`;
    el('path', { d, 'fill-rule': 'evenodd', fill: 'url(#gGreen)', stroke: '#1f4a2c', 'stroke-width': 5 }, front);
    el('rect', { x: W[0], y: W[2], width: W[1] - W[0], height: W[3] - W[2], fill: 'none', stroke: '#1f4a2c', 'stroke-width': 7 }, front);
    // spout mouth ring
    el('rect', { x: S[0] - 5, y: S[2] - 4, width: (S[1] - S[0]) + 10, height: 12, rx: 4, fill: '#1f4a2c' }, front);
    // control lamp
    el('circle', { cx: R.x0 + 26, cy: R.y0 + 26, r: 10, fill: C.gold, opacity: 0.9 }, front);
    // magazine slot marker on left wall (molds slide out to the right on the belt)
    el('rect', { x: R.x0 + 4, y: G.MOLD.hTop - 2, width: 14, height: (G.BELT_BOT - G.MOLD.hTop) + 4, fill: '#12200f', opacity: 0.85 }, front);
    machineBox('funnel', R.x0, R.x1, R.y0, R.y1);
  }

  /* ================= COOLING TUNNEL ================= */
  function buildTunnel() {
    const R = G.TUNNEL;
    const back = V.els['layer-machines-back'], front = V.els['layer-machines-front'];
    el('rect', { x: R.x0, y: R.y0, width: R.x1 - R.x0, height: R.y1 - R.y0, fill: '#22394f' }, back);
    el('rect', { x: R.x0 + 6, y: R.y0 + 6, width: R.x1 - R.x0 - 12, height: R.y1 - R.y0 - 12, fill: 'url(#gFrost)' }, back);
    // cooling coils
    el('line', { x1: R.x0 + 16, y1: R.y0 + 30, x2: R.x1 - 16, y2: R.y0 + 30, stroke: '#7fb2d8', 'stroke-width': 8, 'stroke-linecap': 'round', opacity: 0.7 }, back);
    el('line', { x1: R.x0 + 16, y1: R.y0 + 52, x2: R.x1 - 16, y2: R.y0 + 52, stroke: '#7fb2d8', 'stroke-width': 5, 'stroke-linecap': 'round', opacity: 0.45 }, back);
    // frost mist
    const mist = el('rect', { x: R.x0 + 6, y: R.y0 + 8, width: R.x1 - R.x0 - 12, height: R.y1 - R.y0 - 16, fill: 'url(#gFrost)', opacity: 0.0 }, back);
    V.els.tunnelMist = mist;
    // front face (evenodd): body + entry + exit + window
    const d = `M ${R.x0} ${R.y0} H ${R.x1} V ${R.y1} H ${R.x0} Z
      M ${R.entry[0]} ${R.entry[2]} H ${R.entry[1]} V ${R.entry[3]} H ${R.entry[0]} Z
      M ${R.exit[0]} ${R.exit[2]} H ${R.exit[1]} V ${R.exit[3]} H ${R.exit[0]} Z
      M ${R.win[0]} ${R.win[2]} H ${R.win[1]} V ${R.win[3]} H ${R.win[0]} Z`;
    el('path', { d, 'fill-rule': 'evenodd', fill: 'url(#gIce)', stroke: '#22394f', 'stroke-width': 5 }, front);
    el('rect', { x: R.win[0], y: R.win[2], width: R.win[1] - R.win[0], height: R.win[3] - R.win[2], fill: '#bfe3ff', opacity: 0.10 }, front);
    el('rect', { x: R.win[0], y: R.win[2], width: R.win[1] - R.win[0], height: R.win[3] - R.win[2], fill: 'none', stroke: '#22394f', 'stroke-width': 8 }, front);
    // snowflake marks
    const sf = el('g', { opacity: 0.7 }, front);
    [[3260, 465], [3320, 490], [3380, 462]].forEach(([x, y]) => {
      el('line', { x1: x - 9, y1: y, x2: x + 9, y2: y, stroke: '#bfe3ff', 'stroke-width': 3, 'stroke-linecap': 'round' }, sf);
      el('line', { x1: x, y1: y - 9, x2: x, y2: y + 9, stroke: '#bfe3ff', 'stroke-width': 3, 'stroke-linecap': 'round' }, sf);
      el('line', { x1: x - 6, y1: y - 6, x2: x + 6, y2: y + 6, stroke: '#bfe3ff', 'stroke-width': 2.4, 'stroke-linecap': 'round' }, sf);
      el('line', { x1: x - 6, y1: y + 6, x2: x + 6, y2: y - 6, stroke: '#bfe3ff', 'stroke-width': 2.4, 'stroke-linecap': 'round' }, sf);
    });
    el('rect', { x: R.entry[0] - 4, y: R.entry[2] - 4, width: R.entry[1] - R.entry[0] + 8, height: R.entry[3] - R.entry[2] + 8, fill: 'none', stroke: '#22394f', 'stroke-width': 4 }, front);
    el('rect', { x: R.exit[0] - 4, y: R.exit[2] - 4, width: R.exit[1] - R.exit[0] + 8, height: R.exit[3] - R.exit[2] + 8, fill: 'none', stroke: '#22394f', 'stroke-width': 4 }, front);
    el('rect', { x: R.x0 + 30, y: R.y1 - 6, width: 22, height: G.FLOOR - R.y1 + 6, fill: '#22394f' }, front);
    el('rect', { x: R.x1 - 52, y: R.y1 - 6, width: 22, height: G.FLOOR - R.y1 + 6, fill: '#22394f' }, front);
    machineBox('tunnel', R.x0, R.x1, R.y0, R.y1);
  }

  /* ================= DEMOLD STATION (gantry gripper) + SHELF + BELT-END HOUSING ================= */
  function buildStation() {
    const S = G.STATION, front = V.els['layer-machines-front'], back = V.els['layer-machines-back'];
    // belt-end housing (shell recirculation) — floor standing, FRONT layer so it occludes departing shells
    el('rect', { x: S.beltEnd[0], y: 520, width: S.beltEnd[1] - S.beltEnd[0], height: G.FLOOR - 520, fill: '#39414c' }, front);
    el('rect', { x: S.beltEnd[0] - 6, y: 520, width: S.beltEnd[1] - S.beltEnd[0] + 12, height: 14, rx: 4, fill: '#2c343e' }, front);
    el('rect', { x: S.beltEnd[0] + 6, y: 534, width: 8, height: 60, fill: '#2c343e', opacity: 0.7 }, front);
    // shelf (same top level as belt — Fix 5a: no height gap)
    el('rect', { x: S.shelf[0], y: G.BELT_Y, width: S.shelf[1] - S.shelf[0], height: 14, fill: '#3c3546' }, front);
    el('rect', { x: S.shelf[0], y: G.BELT_Y, width: S.shelf[1] - S.shelf[0], height: 5, fill: '#524a5e' }, front);
    el('rect', { x: S.shelf[0] + 24, y: G.BELT_Y + 14, width: 18, height: G.FLOOR - G.BELT_Y - 14, fill: '#2c2434' }, front);
    el('rect', { x: S.shelf[1] - 60, y: G.BELT_Y + 14, width: 18, height: G.FLOOR - G.BELT_Y - 14, fill: '#2c2434' }, front);
    // gantry: column + arm + brace
    el('rect', { x: S.colX[0], y: S.gantryArmY, width: S.colX[1] - S.colX[0], height: G.FLOOR - S.gantryArmY, fill: '#2f2836' }, back);
    el('rect', { x: S.arm[0], y: S.gantryArmY, width: S.arm[1] - S.arm[0], height: 26, rx: 8, fill: '#3c3546' }, back);
    el('line', { x1: S.colX[0], y1: S.gantryArmY + 26, x2: S.colX[0] - 210, y2: G.FLOOR, stroke: '#2f2836', 'stroke-width': 12 }, back);
    // trolley carriage on the arm + animated stems + claw feet (all attached to gantry)
    const trolley = el('g', {}, front);
    el('rect', { x: -42, y: -12, width: 84, height: 20, rx: 6, fill: '#55606e', stroke: '#39414c', 'stroke-width': 3 }, trolley);
    const stemL = el('line', { x1: -74, y1: 8, x2: -74, y2: 240, stroke: '#4c5560', 'stroke-width': 7 }, front);
    const stemR = el('line', { x1: 74, y1: 8, x2: 74, y2: 240, stroke: '#4c5560', 'stroke-width': 7 }, front);
    const clawL = el('g', {}, front);
    el('rect', { x: -10, y: -26, width: 20, height: 30, rx: 5, fill: '#39414c' }, clawL);
    const clawR = el('g', {}, front);
    el('rect', { x: -10, y: -26, width: 20, height: 30, rx: 5, fill: '#39414c' }, clawR);
    V.els.trolley = trolley; V.els.stemL = stemL; V.els.stemR = stemR; V.els.clawL = clawL; V.els.clawR = clawR;
    machineBox('station-gantry', S.arm[0], S.colX[1], S.gantryArmY, G.FLOOR);
    machineBox('shelf', S.shelf[0], S.shelf[1], G.BELT_Y, G.FLOOR);
  }

  /* ================= PRODUCTS ================= */
  function buildProducts() {
    const pr = V.els['layer-products'];
    // bean clusters (raw, entering roaster)
    const rnd = mulberry32(303);
    const clusters = [];
    for (let k = 0; k < 6; k++) {
      const g = el('g', {}, pr);
      const offs = [];
      for (let i = 0; i < 6; i++) {
        offs.push({ dx: i * 24 + rnd() * 10 - 5, dy: rnd() * 8 - 4, rot: rnd() * 40 - 20 });
      }
      clusters.push({ g, offs, t0: 2.5 + 2.0 * k });
      offs.forEach(o => {
        el('ellipse', { cx: 0, cy: 0, rx: 13, ry: 9, fill: C.beanRaw, transform: `rotate(${o.rot})` }, g);
        el('line', { x1: -6, y1: -2, x2: 6, y2: -2, stroke: '#33200f', 'stroke-width': 2 }, g);
      });
    }
    V.els.beanClusters = clusters;
    // roasted clusters exiting roaster
    const roasted = [];
    for (let k = 0; k < 2; k++) {
      const g = el('g', {}, pr);
      const offs = [];
      const rr = mulberry32(404 + k);
      for (let i = 0; i < 5; i++) offs.push({ dx: i * 26 + rr() * 8 - 4, dy: rr() * 8 - 4 });
      offs.forEach(o => el('ellipse', { cx: 0, cy: 0, rx: 13, ry: 9, fill: C.beanRoast }, g));
      roasted.push({ g, offs, t0: 21.2 + 1.4 * k });
    }
    V.els.roastedClusters = roasted;
    // paste lump
    const lump = el('g', {}, pr);
    el('ellipse', { cx: 0, cy: -12, rx: 27, ry: 15, fill: C.paste }, lump);
    el('ellipse', { cx: -8, cy: -16, rx: 10, ry: 5, fill: '#5f4028', opacity: 0.8 }, lump);
    V.els.pasteLump = lump;
    // molds (3): shell + bar(+fill)
    const molds = [];
    for (let i = 0; i < 3; i++) {
      const shellG = el('g', {}, pr);
      const M = G.MOLD;
      // U shell: bottom plate + side walls
      el('rect', { x: 0, y: M.hBot, width: M.w, height: 16, rx: 4, fill: C.shell }, shellG);
      el('rect', { x: 0, y: M.hTop, width: M.wall, height: (M.hBot - M.hTop) + 16, rx: 3, fill: C.shell }, shellG);
      el('rect', { x: M.w - M.wall, y: M.hTop, width: M.wall, height: (M.hBot - M.hTop) + 16, rx: 3, fill: C.shell }, shellG);
      el('rect', { x: M.wall, y: M.hBot - 3, width: M.w - 2 * M.wall, height: 3, fill: C.shellIn }, shellG);
      // dynamic clip for fill/bar
      const clipId = 'moldFillClip' + 'ABC'[i];
      const cr = document.getElementById(clipId).firstChild;
      // bar/fill rect (clipped to shell interior while in mold)
      const barG = el('g', { 'clip-path': `url(#${clipId})` }, pr);
      const fill = el('rect', { x: 0, y: M.hBot, width: M.w - 2 * M.wall, height: 0, fill: 'url(#gLiquid)' }, barG);
      const solid = el('rect', { x: 0, y: M.hBot, width: M.w - 2 * M.wall, height: 0, fill: 'url(#gBar)', opacity: 0 }, barG);
      const sheen = el('rect', { x: 0, y: M.barTop + 8, width: M.w - 2 * M.wall, height: 6, rx: 3, fill: '#c89a6a', opacity: 0 }, barG);
      molds.push({ i, shellG, barG, fill, solid, sheen, clipRect: cr });
      shellG.setAttribute('opacity', 0);
      barG.setAttribute('opacity', 0);
    }
    V.els.molds = molds;
    // pour thread (per mold, above mold) — strictly between spout and mold surface
    const threads = [];
    for (let i = 0; i < 3; i++) {
      const th = el('path', { d: '', fill: 'none', stroke: 'url(#gLiquid)', 'stroke-width': 10, 'stroke-linecap': 'round', opacity: 0 }, pr);
      threads.push(th);
    }
    V.els.threads = threads;
    // splash rings
    const splash = [];
    for (let i = 0; i < 3; i++) {
      const sp = el('ellipse', { cx: 0, cy: 0, rx: 10, ry: 4, fill: C.liquidHi, opacity: 0 }, pr);
      splash.push(sp);
    }
    V.els.splash = splash;
    // tunnel mold silhouettes (clipped to tunnel interior)
    const tClip = document.getElementById('tunnelInteriorRect');
    tClip.setAttribute('x', G.TUNNEL.x0 + 4); tClip.setAttribute('y', G.MOLD.hTop - 2);
    tClip.setAttribute('width', G.TUNNEL.x1 - G.TUNNEL.x0 - 8); tClip.setAttribute('height', (G.BELT_BOT - G.MOLD.hTop) + 2);
    const tG = el('g', { 'clip-path': 'url(#tunnelInteriorClip)' }, V.els['layer-products-back']);
    const tSil = [];
    for (let i = 0; i < 3; i++) {
      const g = el('g', { opacity: 0 }, tG);
      el('rect', { x: 0, y: G.MOLD.hTop + 20, width: G.MOLD.w - 2 * G.MOLD.wall, height: G.MOLD.hBot - G.MOLD.hTop - 20, rx: 5, fill: '#274b66', opacity: 0.85 }, g);
      tSil.push(g);
    }
    V.els.tunnelSils = tSil;
  }

  /* ================= EFFECTS ================= */
  function buildEffects() {
    const ef = V.els['layer-effects'];
    // tank steam (3 puffs, deterministic loop)
    const steam = [];
    for (let i = 0; i < 3; i++) {
      const g = el('g', { opacity: 0 }, ef);
      el('ellipse', { cx: 0, cy: 0, rx: 26, ry: 14, fill: '#e8dcc8', opacity: 0.16 }, g);
      el('ellipse', { cx: 10, cy: -12, rx: 16, ry: 9, fill: '#e8dcc8', opacity: 0.12 }, g);
      steam.push({ g, seed: i * 77 });
    }
    V.els.steam = steam;
    // roast shimmer above chimney
    const shim = el('g', { opacity: 0 }, ef);
    for (let i = 0; i < 3; i++) {
      el('ellipse', { cx: 0, cy: -i * 26, rx: 20 - i * 4, ry: 10 - i * 2, fill: '#e8dcc8', opacity: 0.10 }, shim);
    }
    V.els.shimmer = shim;
    // tunnel sparkles
    const sparks = [];
    const rnd = mulberry32(505);
    for (let i = 0; i < 5; i++) {
      const x = G.TUNNEL.win[0] + 30 + rnd() * (G.TUNNEL.win[1] - G.TUNNEL.win[0] - 60);
      const y = G.TUNNEL.win[2] + 20 + rnd() * (G.TUNNEL.win[3] - G.TUNNEL.win[2] - 40);
      const s = el('path', { d: `M ${x} ${y - 5} L ${x + 1.6} ${y - 1.6} L ${x + 5} ${y} L ${x + 1.6} ${y + 1.6} L ${x} ${y + 5} L ${x - 1.6} ${y + 1.6} L ${x - 5} ${y} L ${x - 1.6} ${y - 1.6} Z`, fill: '#d8ecff', opacity: 0 }, ef);
      sparks.push({ s, ph: rnd() * 6.28 });
    }
    V.els.sparks = sparks;
    // grinder dust
    const dust = [];
    for (let i = 0; i < 3; i++) {
      const g = el('g', { opacity: 0 }, ef);
      el('ellipse', { cx: 0, cy: 0, rx: 14, ry: 8, fill: '#d8c8b8', opacity: 0.10 }, g);
      dust.push({ g, ph: i * 2.3 });
    }
    V.els.dust = dust;
  }

  /* ================= BANNERS (world space, layer-labels) ================= */
  function buildBanners() {
    const L = V.els['layer-labels'];
    const defs = [
      [G.ROASTER.banner, 'طبلية التحميص'],
      [G.GRINDER.banner, 'أسطانة الطحن'],
      [G.TANK.banner, 'المعالجة والخلط'],
      [G.FUNNEL.banner, 'الصب في القوالب'],   // Fix 6
      [G.TUNNEL.banner, 'نفق التبريد']          // Fix 6
    ];
    const groups = [];
    defs.forEach(([pos, label]) => {
      const g = el('g', { 'class': 've2-banner' }, L);
      const t = el('text', { x: pos[0], y: pos[1], 'text-anchor': 'middle', 'font-size': 30, 'font-weight': 700, fill: C.cream }, g, label);
      groups.push({ g, t, pos });
    });
    V.els.bannerGroups = groups;
  }

  /* measure banner capsules after fonts are ready (GBCR-based = real layout box) */
  function sizeBanners() {
    V.els.bannerGroups.forEach(({ g, t, pos }) => {
      const r1 = t.getBoundingClientRect();
      const w = r1.width + 52, h = 52;
      const r = el('rect', { x: pos[0] - w / 2, y: pos[1] - h + 10, width: w, height: h, rx: 17, fill: '#14101a', opacity: 0.92, stroke: C.gold, 'stroke-opacity': 0.5, 'stroke-width': 2 }, g);
      g.insertBefore(r, t);
    });
  }

  /* ================= SCREEN UI: title / chip / end card / hero bar ================= */
  function buildTitle() {
    const g = V.els['title-card'];
    g.setAttribute('opacity', 0);
    // gold cocoa bean icon
    const bean = el('g', { transform: 'translate(540 200) rotate(-14)' }, g);
    el('ellipse', { cx: 0, cy: 0, rx: 46, ry: 62, fill: C.gold }, bean);
    el('path', { d: 'M 0 -62 Q 26 0 0 62', fill: 'none', stroke: '#8a6a20', 'stroke-width': 5 }, bean);
    el('path', { d: 'M -18 -40 Q -34 0 -18 40', fill: 'none', stroke: '#caa23a', 'stroke-width': 4, opacity: 0.7 }, bean);
    const t1 = el('text', { x: 540, y: 330, 'text-anchor': 'middle', 'font-size': 74, 'font-weight': 700, fill: C.cream }, g, 'كيف تُصنع الشوكولاتة');
    // pill "من الصفر"
    const pill = el('g', {}, g);
    const tp = el('text', { x: 540, y: 424, 'text-anchor': 'middle', 'font-size': 42, 'font-weight': 700, fill: '#1d1420' }, pill, 'من الصفر');
    V.els.titleParts = { g, bean, t1, pill, tp };
  }
  function sizeTitle() {
    const { t1, pill, tp } = V.els.titleParts;
    const bb = tp.getBoundingClientRect();
    const w = bb.width + 64, h = 66;
    const r = el('rect', { x: 540 - w / 2, y: 424 - h + 13, width: w, height: h, rx: h / 2, fill: C.gold }, pill);
    pill.insertBefore(r, tp);
  }

  const CHIPS = [
    { t0: 14.35, t1: 24.85, num: '02', label: 'التحميص' },
    { t0: 24.85, t1: 36.90, num: '03', label: 'الطحن' },
    { t0: 36.90, t1: 44.17, num: '04', label: 'المعالجة والخلط' },
    { t0: 44.17, t1: 54.40, num: '05', label: 'الصب والتبريد' }
  ];
  function buildChips() {
    const root = V.els['stage-chip'];
    const groups = [];
    CHIPS.forEach(c => {
      const g = el('g', { opacity: 0 }, root);
      // anchor middle at x=0; final x computed from measured width in sizeChips (anchor-agnostic)
      const t = el('text', { x: 0, y: 148, 'text-anchor': 'middle', 'font-size': 38, 'font-weight': 700, fill: C.cream }, g, c.label);
      const bean = el('g', {}, g);
      el('ellipse', { cx: 0, cy: 0, rx: 30, ry: 38, fill: C.gold, transform: 'rotate(-12)' }, bean);
      el('path', { d: 'M 0 -38 Q 16 0 0 38', fill: 'none', stroke: '#8a6a20', 'stroke-width': 4 }, bean);
      const tn = el('text', { x: 0, y: 12, 'text-anchor': 'middle', 'font-size': 30, 'font-weight': 700, fill: '#1d1420' }, bean, c.num);
      groups.push({ g, t, bean, tn, c });
    });
    V.els.chipGroups = groups;
  }
  function sizeChips() {
    V.els.chipGroups.forEach(({ g, t, bean }) => {
      bean.setAttribute('transform', `translate(528 133)`);
      // desired: text RIGHT edge at 474 (bean bbox starts ~491, 16px buffer)
      const desiredRight = 474;
      t.setAttribute('x', '0');
      const w = t.getBoundingClientRect().width;   // real layout width
      t.setAttribute('x', String(474 - w / 2));
      // pass 2: exact correction from the REAL laid-out rect
      const r1 = t.getBoundingClientRect();
      if (Math.abs(r1.right - desiredRight) > 0.5) {
        const cur = parseFloat(t.getAttribute('x'));
        t.setAttribute('x', String(cur - (r1.right - desiredRight)));
      }
      const w2 = Math.max(w, t.getBoundingClientRect().width) + 96;
      const r = el('rect', { x: 574 - w2, y: 96, width: w2, height: 74, rx: 24, fill: '#14101a', opacity: 0.9, stroke: C.gold, 'stroke-opacity': 0.45, 'stroke-width': 2 }, g);
      g.insertBefore(r, t);
    });
  }

  function buildEndCard() {
    const g = V.els['end-card'];
    g.setAttribute('opacity', 0);
    const panel = el('rect', { x: 150, y: 520, width: 780, height: 470, rx: 30, fill: '#0d0a12', opacity: 0.66, stroke: C.gold, 'stroke-opacity': 0.4, 'stroke-width': 2.5 }, g);
    V.els.endPanel = panel;
    const l1 = el('text', { x: 540, y: 640, 'text-anchor': 'middle', 'font-size': 62, 'font-weight': 700, fill: C.cream, 'class': 'ar' }, g, 'من حبة الكاكاو');
    const l2 = el('text', { x: 540, y: 742, 'text-anchor': 'middle', 'font-size': 62, 'font-weight': 700, fill: C.gold, 'class': 'ar' }, g, 'إلى لوح الشوكولاتة');
    el('rect', { x: 390, y: 782, width: 300, height: 5, rx: 2.5, fill: C.gold, opacity: 0.75 }, g);
    // Fix 4: subtitle split into two lines, safe margins enforced & verified
    const s1 = el('text', { x: 540, y: 862, 'text-anchor': 'middle', 'font-size': 41, 'font-weight': 400, fill: C.sub, 'class': 'ar' }, g, 'تحميص وطحن ومعالجة وصب');
    const s2 = el('text', { x: 540, y: 926, 'text-anchor': 'middle', 'font-size': 41, 'font-weight': 400, fill: C.sub, 'class': 'ar' }, g, 'كل ذلك على خط واحد');
    V.els.endLines = [l1, l2, s1, s2];
  }

  function buildHeroBar() {
    const g = V.els['hero-bar'];
    g.setAttribute('opacity', 0);
    const bar = el('g', {}, g);
    el('rect', { x: 305, y: 1128, width: 470, height: 244, rx: 20, fill: 'url(#gBar)', stroke: '#2e1a0c', 'stroke-width': 6 }, bar);
    for (let r = 0; r < 3; r++) for (let c = 0; c < 5; c++) {
      el('rect', { x: 329 + c * 86, y: 1152 + r * 74, width: 70, height: 58, rx: 10, fill: '#6d4526', stroke: '#4a2c15', 'stroke-width': 3 }, bar);
      el('rect', { x: 336 + c * 86, y: 1158 + r * 74, width: 40, height: 12, rx: 6, fill: '#8a5a33', opacity: 0.65 }, bar);
    }
    el('rect', { x: 320, y: 1140, width: 120, height: 10, rx: 5, fill: '#c89a6a', opacity: 0.5 }, bar);
    V.els.heroBarG = g;
  }

  /* ================= INIT ================= */
  function init() {
    ['layer-bg', 'layer-belt-back', 'layer-machines-back', 'layer-products-back', 'layer-products', 'layer-machines-front', 'layer-effects', 'layer-labels',
     'title-card', 'stage-chip', 'end-card', 'hero-bar', 'caption-root'].forEach(id => { V.els[id] = document.getElementById(id); });
    V.els.camera = document.getElementById('camera');
    V.els.worldRoot = document.getElementById('worldRoot');
    // worldClipRect dimensions are set in scene.html defs (covers full zoom range)

    buildBG(); buildBelt(); buildRoaster(); buildGrinder(); buildTank(); buildPipe(); buildFunnel(); buildTunnel(); buildStation(); buildProducts(); buildEffects();
    buildTitle(); buildChips(); buildEndCard(); buildHeroBar();
    buildBanners();

    let inited = false;
    const done = () => {
      if (inited) return;
      inited = true;
      sizeBanners(); sizeTitle(); sizeChips();
      if (window.VE2Captions && window.VE2Captions.init) window.VE2Captions.init();
      window.__ve2Ready = true;
    };
    // CRITICAL: explicitly trigger the Tajawal loads (fonts.ready may resolve before lazy loads start)
    if (document.fonts && document.fonts.load) {
      const specs = ['400 40px Tajawal', '700 30px Tajawal', '700 40px Tajawal', '700 66px Tajawal', '700 74px Tajawal', '400 41px Tajawal'];
      Promise.all(specs.map(s => document.fonts.load(s, 'نص عربي للقياس'))).then(done).catch(done);
      setTimeout(done, 2500);
    } else setTimeout(done, 400);
  }
  window.__ve2Init = init;
})();
