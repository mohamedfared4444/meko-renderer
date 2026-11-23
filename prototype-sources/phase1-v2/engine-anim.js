/* VE2 engine-anim.js — deterministic state machine (dirty-checked writes).
   renderAt(t) computes the ENTIRE frame from absolute time t (pure function).
   S() skips attribute writes whose value is unchanged → no needless paint
   invalidation → byte-identical re-renders of the same t (raster-cache safe).
   No Math.random, no timers, no previous-frame logic state. */
(function () {
  'use strict';
  const V = window.VE2, G = V.G, E = V.els;
  const SPEED = G.SPEED;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const ss = u => { u = clamp(u, 0, 1); return u * u * (3 - 2 * u); };
  const eoc = u => 1 - Math.pow(1 - clamp(u, 0, 1), 3);
  const eio = u => { u = clamp(u, 0, 1); return u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2; };

  /* dirty-checked attribute write */
  function S(el, attr, val) {
    const s = String(val);
    let c = el.__ve2c;
    if (!c) { c = {}; el.__ve2c = c; }
    if (c[attr] !== s) { c[attr] = s; el.setAttribute(attr, s); }
  }
  /* set transform only (helper alias) */
  const T = (el, val) => S(el, 'transform', val);
  const O = (el, val) => S(el, 'opacity', val);
  V.S = S; V.T = T; V.O = O;

  /* ---------------- camera keys ---------------- */
  const KEYS = [
    [0.00, 260, 430, 1.00], [4.00, 340, 440, 1.02], [13.60, 480, 445, 1.00],
    [14.35, 850, 505, 1.85], [19.50, 862, 515, 1.90], [24.30, 965, 530, 1.80],
    [24.85, 1520, 505, 1.75], [30.00, 1545, 515, 1.80], [33.20, 1630, 528, 1.70],
    [36.90, 2180, 505, 1.55], [40.00, 2365, 470, 1.22], [44.17, 2560, 492, 1.10],
    [44.70, 2700, 512, 1.45], [48.00, 2830, 518, 1.42], [50.20, 3090, 515, 1.30],
    [54.40, 3630, 540, 1.30], [55.90, 3770, 545, 1.25],
    [55.90, 3400, 505, 0.62], [57.50, 2500, 500, 0.40], [60.70, 2450, 500, 0.315]
  ];
  function cameraAt(t) {
    let i = 0;
    while (i + 1 < KEYS.length && KEYS[i + 1][0] <= t) i++;
    const a = KEYS[i], b = KEYS[Math.min(i + 1, KEYS.length - 1)];
    const span = b[0] - a[0];
    const u = span > 0 ? ss((t - a[0]) / span) : 0;
    return [a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u, a[3] + (b[3] - a[3]) * u];
  }

  /* ---------------- mold schedule (non-overlap constrained) ---------------- */
  const MOLDS = [0, 1, 2].map(i => {
    const emerge = [44.6, 47.55, 50.75][i];
    const tStop = emerge + 0.25;
    const f0 = tStop + 0.35, f1 = f0 + 1.3;
    const depart = tStop + 2.05;
    const tArr = depart + 5.225;
    const grip0 = tArr + 0.15, lift0 = grip0 + 0.25, lift1 = lift0 + 0.35;
    const trav0 = lift1, trav1 = trav0 + 0.5;
    const low0 = trav1, low1 = low0 + 0.35;
    return { i, emerge, tStop, f0, f1, depart, tArr, grip0, lift0, lift1, trav0, trav1, low0, low1, shellGo: low1 + 0.05, target: 3940 + i * 135 };
  });

  function funnelLevel(t) {
    let lvl = clamp((t - 40.3) / 4.1, 0, 1);
    MOLDS.forEach(m => {
      const dip = 0.12 * (clamp((t - m.f0) / (m.f1 - m.f0), 0, 1) - clamp((t - m.f1) / 1.0, 0, 1));
      lvl -= dip;
    });
    return clamp(lvl, 0, 1);
  }

  function moldState(m, t) {
    const M = G.MOLD;
    let shellX = null;
    if (t >= m.emerge && t < m.tStop) shellX = 2605 + (t - m.emerge) / 0.25 * 20;
    else if (t >= m.tStop && t < m.depart) shellX = 2625;
    else if (t >= m.depart && t < m.tArr) shellX = 2625 + (t - m.depart) * SPEED;
    else if (t >= m.tArr && t < m.shellGo) shellX = 3670;
    else if (t >= m.shellGo && t < m.shellGo + 0.85) shellX = 3670 + (t - m.shellGo) * SPEED;
    const visible = shellX !== null && shellX <= 3852;

    const fu = clamp((t - m.f0) / 1.3, 0, 1);
    const fillH = 74 * fu;
    const surfY = 640 - fillH;

    let barLeft, barTop, clipped = true;
    if (t < m.lift0) { barLeft = shellX + 12; barTop = 584; }
    else if (t < m.lift1) { barLeft = 3682; barTop = 584 - 130 * eoc((t - m.lift0) / 0.35); clipped = false; }
    else if (t < m.trav1) { barLeft = 3682 + (m.target - 3682) * eio((t - m.trav0) / 0.5); barTop = 454; clipped = false; }
    else if (t < m.low1) { barLeft = m.target; barTop = 454 + 130 * eoc((t - m.low0) / 0.35); clipped = false; }
    else if (t >= m.low1) { barLeft = m.target; barTop = 584; clipped = false; }
    if (shellX === null) { barLeft = -500; barTop = 584; }

    const solidU = (shellX !== null && shellX > 3080) ? clamp((shellX - 3160) / 300, 0, 1) : (t >= m.lift0 ? 1 : 0);
    return { shellX, visible, fillH, surfY, barLeft, barTop, clipped, solidU, fu };
  }

  function renderAt(t) {
    /* camera */
    const [cx, cy, s] = cameraAt(t);
    T(E.camera, `translate(540 960) scale(${s.toFixed(5)}) translate(${(-cx).toFixed(2)} ${(-cy).toFixed(2)})`);

    /* Phase 2 parallax: far layer follows camera at 0.35x, mid at 0.65x
       (counter-translate cx*(1-f) inside the camera group => effective camera cx*f) */
    if (E.plxFar) T(E.plxFar, `translate(${(cx * 0.65).toFixed(2)} ${(cy * 0.65).toFixed(2)})`);
    if (E.plxMid) T(E.plxMid, `translate(${(cx * 0.35).toFixed(2)} ${(cy * 0.35).toFixed(2)})`);

    /* belt + rollers */
    S(E.beltDash, 'stroke-dashoffset', String(-((t * SPEED) % 64)));
    const ra = ((t * 160) % 360).toFixed(2);
    E.rollers.forEach(r => {
      const cx0 = r.getAttribute('cx'), cy0 = r.getAttribute('cy');
      T(r, `rotate(${ra} ${cx0} ${cy0})`);
    });

    /* raw bean clusters */
    E.beanClusters.forEach(c => {
      if (t < c.t0) { O(c.g, 0); return; }
      const x = -80 + (t - c.t0) * SPEED;
      if (x > 658) { O(c.g, 0); return; }
      O(c.g, 1);
      T(c.g, `translate(${x.toFixed(1)} 626)`);
    });
    /* roasted clusters */
    E.roastedClusters.forEach(c => {
      if (t < c.t0) { O(c.g, 0); return; }
      const x = 1085 + (t - c.t0) * SPEED;
      if (x < 1085 || x > 1305) { O(c.g, 0); return; }
      O(c.g, 1);
      T(c.g, `translate(${x.toFixed(1)} 626)`);
    });

    /* grinder */
    T(E.grindRollers[0], `rotate(${(t * 210).toFixed(2)} 1455 520)`);
    T(E.grindRollers[1], `rotate(${(-t * 210).toFixed(2)} 1585 520)`);
    E.grindParts.forEach(p => {
      const prog = (t * 0.85 + p.ph / 130) % 1;
      S(p.p, 'cx', String(1520 + p.ox));
      S(p.p, 'cy', String(594 + prog * 46));
    });
    const pl = clamp((t - 27.5) / 5.5, 0, 1);
    S(E.pasteLvl, 'y', String(640 - 40 * pl));
    S(E.pasteLvl, 'height', String(40 * pl));

    /* paste lump */
    if (t >= 33.5) {
      const x = 1720 + Math.max(0, t - 33.8) * SPEED;
      if (x <= 1975) { O(E.pasteLump, 1); T(E.pasteLump, `translate(${x.toFixed(1)} 628)`); }
      else O(E.pasteLump, 0);
    } else O(E.pasteLump, 0);

    /* tank */
    const tlvl = 0.25 + 0.7 * clamp((t - 36.5) / 3.0, 0, 1);
    const surf = 640 - 100 * tlvl;
    const liqMix = clamp((t - 37.5) / 3.0, 0, 1);
    S(E.tankLvlPaste, 'y', String(surf)); S(E.tankLvlPaste, 'height', String(640 - surf));
    O(E.tankLvlPaste, 1 - liqMix);
    S(E.tankLvlLiq, 'y', String(surf)); S(E.tankLvlLiq, 'height', String(640 - surf));
    O(E.tankLvlLiq, liqMix);
    S(E.tankSurf, 'y', String(surf - 2));
    S(E.tankSwirl, 'cy', String(surf + 16));
    S(E.tankSwirl, 'rx', String(120 + 10 * Math.sin(t * 2.1)));
    O(E.tankSwirl, 0.2 * clamp((t - 37) / 2, 0, 1));
    // rich specular gloss on the liquid (deterministic drift)
    if (E.tankGloss) {
      O(E.tankGloss, 0.10 * clamp((t - 37.5) / 3, 0, 1));
      S(E.tankGloss, 'cy', String(surf - 8 + 2 * Math.sin(t * 1.7)));
      S(E.tankGloss, 'cx', String(2100 + 14 * Math.sin(t * 0.9)));
    }
    T(E.agitArm, `rotate(${(t * 135).toFixed(2)} 2180 566)`);

    /* roaster temperature dial needle (slow deterministic sweep) */
    if (E.roastNeedle) {
      const na = 8 * Math.sin(t * 0.7);
      T(E.roastNeedle, `rotate(${na.toFixed(2)} 740 446)`);
    }

    /* pipe liquid (strictly inside pipe interior clip) */
    const flowActive = t >= 39.8 && t <= 52.8;
    O(E.pipeLiq, flowActive ? 1 : 0);
    O(E.pipeLiqHi, flowActive ? 0.75 : 0);
    if (flowActive) {
      S(E.pipeLiq, 'stroke-dashoffset', String(-((t * 130) % 44)));
      S(E.pipeLiqHi, 'stroke-dashoffset', String(-((t * 130) % 44)));
    }

    /* funnel level */
    const flvl = funnelLevel(t);
    S(E.funLvl, 'y', String(545 - 152 * flvl));
    S(E.funLvl, 'height', String(152 * flvl));
    S(E.funSurf, 'y', String(545 - 152 * flvl));

    /* molds + threads + splash */
    MOLDS.forEach(m => {
      const st = moldState(m, t);
      const M = G.MOLD, mo = E.molds[m.i];
      if (st.visible) {
        O(mo.shellG, 1);
        T(mo.shellG, `translate(${st.shellX.toFixed(1)} 0)`);
      } else O(mo.shellG, 0);

      const wantClip = st.clipped;
      if (mo.clippedState !== wantClip) {
        mo.clippedState = wantClip;
        if (wantClip) {
          S(mo.clipRect, 'x', String(st.shellX + 12));
          S(mo.clipRect, 'y', String(M.hTop));
          S(mo.clipRect, 'width', String(M.w - 24));
          S(mo.clipRect, 'height', String(M.hBot - M.hTop));
          S(mo.barG, 'clip-path', `url(#moldFillClip${'ABC'[m.i]})`);
        } else S(mo.barG, 'clip-path', 'none');
      }
      if (wantClip) S(mo.clipRect, 'x', String(st.shellX + 12));

      const fullH = Math.max(st.fillH, t >= m.f1 ? 74 : st.fillH);
      const barVis = (st.fillH > 0.5 || t >= m.f1) && st.shellX !== null;
      O(mo.barG, barVis ? 1 : 0);
      S(mo.fill, 'x', String(st.barLeft));
      S(mo.fill, 'y', String(640 - fullH));
      S(mo.fill, 'height', String(fullH));
      S(mo.solid, 'x', String(st.barLeft));
      S(mo.solid, 'y', String(640 - fullH));
      S(mo.solid, 'height', String(fullH));
      O(mo.solid, st.solidU);
      S(mo.sheen, 'x', String(st.barLeft + 8));
      S(mo.sheen, 'y', String(st.barTop + 8));
      O(mo.sheen, st.solidU * 0.55);

      const th = E.threads[m.i];
      const thi = E.threadHis ? E.threadHis[m.i] : null;
      const pouring = t >= m.f0 && t <= m.f1 + 0.15 && st.shellX !== null;
      if (pouring) {
        const surfY = st.surfY;
        const mid = 2700 + Math.sin(t * 9 + m.i) * 2.5;
        S(th, 'd', `M 2700 549 Q ${mid.toFixed(1)} ${((549 + surfY - 2) / 2).toFixed(1)} 2700 ${(surfY - 2).toFixed(1)}`);
        O(th, t > m.f1 ? (m.f1 + 0.15 - t) / 0.15 : 1);
        if (thi) {
          S(thi, 'd', `M 2696 549 Q ${(mid - 4).toFixed(1)} ${((549 + surfY - 2) / 2).toFixed(1)} 2696 ${(surfY - 2).toFixed(1)}`);
          O(thi, (t > m.f1 ? (m.f1 + 0.15 - t) / 0.15 : 1) * 0.6);
        }
      } else { O(th, 0); if (thi) O(thi, 0); }

      const sp = E.splash[m.i];
      const su = clamp((t - m.f0) / 0.45, 0, 1);
      if (su > 0 && su < 1 && st.shellX !== null) {
        S(sp, 'cx', '2700'); S(sp, 'cy', String(st.surfY - 3));
        S(sp, 'rx', String(8 + 18 * su)); S(sp, 'ry', String(3 + 6 * su));
        O(sp, 0.5 * (1 - su));
      } else O(sp, 0);

      /* Phase 2: beveled-squares decor visible only when the bar landed on shelf */
      if (mo.decor) {
        const landed = (!st.clipped) && st.barTop >= 584 && st.fillH >= 73.5 &&
          st.barLeft === m.target;
        O(mo.decor, landed ? st.solidU : 0);
        if (landed) T(mo.decor, `translate(${st.barLeft.toFixed(1)} ${(640 - 74).toFixed(1)})`);
      }
    });

    /* gantry gripper */
    const am = activeStationMold(t);
    if (am !== null) {
      const m = MOLDS[am];
      const tg = t;
      const bx = tg < m.lift1 ? 3682 + (tg >= m.trav0 ? (m.target - 3682) * eio((tg - m.trav0) / 0.5) : 0) : m.target;
      const btop = tg < m.lift1 ? (tg >= m.lift0 ? 584 - 130 * eoc((tg - m.lift0) / 0.35) : 584)
        : (tg < m.low1 ? 454 + 130 * eoc((tg - m.low0) / 0.35) : 584);
      const barCX = bx + 63, clawY = btop + 4;
      T(E.trolley, `translate(${barCX.toFixed(1)} 342)`);
      S(E.stemL, 'x1', String(barCX - 74)); S(E.stemL, 'x2', String(barCX - 74));
      S(E.stemR, 'x1', String(barCX + 74)); S(E.stemR, 'x2', String(barCX + 74));
      S(E.stemL, 'y2', String(clawY - 26));
      S(E.stemR, 'y2', String(clawY - 26));
      T(E.clawL, `translate(${(barCX - 74).toFixed(1)} ${clawY.toFixed(1)})`);
      T(E.clawR, `translate(${(barCX + 74).toFixed(1)} ${clawY.toFixed(1)})`);
    } else {
      T(E.trolley, 'translate(3760 342)');
      S(E.stemL, 'x1', '3686'); S(E.stemL, 'x2', '3686'); S(E.stemL, 'y2', '380');
      S(E.stemR, 'x1', '3834'); S(E.stemR, 'x2', '3834'); S(E.stemR, 'y2', '380');
      T(E.clawL, 'translate(3686 406)');
      T(E.clawR, 'translate(3834 406)');
    }

    /* steam / shimmer / dust / sparks / mist */
    /* steam INSIDE the tank window (clipped: never above the roof — inlet fix) */
    const steamMaster = clamp((t - 36.9) * 2, 0, 1) * (1 - clamp((t - 44.0) * 3, 0, 1));
    E.steam.forEach(p => {
      const cyc = (t * 0.22 + p.seed * 0.0137) % 1;
      T(p.g, `translate(${(2180 + Math.sin(cyc * 7 + p.seed) * 60).toFixed(1)} ${(618 - cyc * 112).toFixed(1)})`);
      O(p.g, Math.sin(cyc * Math.PI) * 0.85 * steamMaster);
    });
    const shimMaster = clamp((t - 15.0) * 2, 0, 1) * (1 - clamp((t - 24.2) * 3, 0, 1));
    const shimCyc = (t * 0.3) % 1;
    T(E.shimmer, `translate(957 ${(236 - shimCyc * 40).toFixed(1)})`);
    O(E.shimmer, shimMaster * (1 - shimCyc) * 0.9);
    const dustMaster = clamp((t - 25.4) * 2, 0, 1) * (1 - clamp((t - 36.3) * 3, 0, 1));
    E.dust.forEach(d => {
      const cyc = (t * 0.3 + d.ph) % 1;
      T(d.g, `translate(${(1520 + Math.sin(cyc * 6 + d.ph * 3) * 46).toFixed(1)} ${(560 - 40 * cyc).toFixed(1)})`);
      O(d.g, dustMaster * (1 - cyc) * 0.9);
    });
    E.sparks.forEach(sp2 => O(sp2.s, 0.18 + 0.3 * Math.max(0, Math.sin(t * 2.6 + sp2.ph))));
    O(E.tunnelMist, 0.35 + 0.25 * Math.sin(t * 1.2));

    /* title */
    const tu = clamp((t - 0.3) / 0.6, 0, 1);
    const tout = 1 - clamp((t - 13.6) / 0.55, 0, 1);
    const titleG = E.titleParts.g;
    O(titleG, tu * tout);
    T(titleG, `translate(0 ${(30 * (1 - eoc(tu))).toFixed(1)})`);

    /* chips */
    E.chipGroups.forEach(({ g, c }) => {
      const op = clamp((t - c.t0 - 0.35) / 0.3, 0, 1) * (1 - clamp((t - (c.t1 - 0.45)) / 0.4, 0, 1));
      O(g, op);
    });

    /* end card */
    const eu = clamp((t - 57.0) / 0.5, 0, 1);
    const endG = document.getElementById('end-card');
    O(endG, eu);
    T(endG, `translate(0 ${(26 * (1 - eoc(eu))).toFixed(1)})`);

    /* hero bar */
    const hu = clamp((t - 56.0) / 0.4, 0, 1);
    const hg = E.heroBarG;
    O(hg, hu);
    const hscale = 0.86 + 0.14 * eoc(hu);
    const hdy = 46 * (1 - eoc(hu));
    T(hg, `translate(0 ${hdy.toFixed(1)}) translate(540 1250) scale(${hscale.toFixed(4)}) translate(-540 -1250)`);

    /* captions */
    window.VE2Captions.update(t);
  }

  function activeStationMold(t) {
    for (const m of MOLDS) {
      if (t >= m.grip0 && t <= m.low1 + 0.45) return m.i;
    }
    return null;
  }

  window.__ve2 = { renderAt, G, KEYS, MOLDS, cameraAt };

  /* boot */
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', window.__ve2Init);
  else window.__ve2Init();
})();
