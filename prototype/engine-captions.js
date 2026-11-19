/* VE2 engine-captions.js — TRUE Single-Pop captions (Phase 1.1 Fix 1).
   At most ONE chunk (1-2 words) visible at any instant.
   - Chunks derived deterministically from word timings.
   - Short function words bind to the NEXT word (RTL natural grouping).
   - Instant swap at the next chunk's start; short fade only into silence.
   - Dark capsule + clear bold Tajawal, active word gold while spoken.
   - DOM built ONCE; per-frame updates are opacity/fill attributes only. */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const GOLD = '#FFC94D', CREAM = '#F3E9D8';
  const BASE_Y = 1646;          // caption text baseline (bottom safe area)
  const MAX_W = 860;            // max chunk width before font shrink
  const FONT = 66;
  const FUNC = new Set(['من', 'في', 'على', 'لحد', 'اللي', 'بين', 'مع', 'أو', 'او', 'و', 'ف', 'يا', 'كل', 'ده', 'دي', 'إلى', 'الى', 'عشان', 'علشان', 'حتى', 'لكن', 'ثم']);

  function coreWord(w) {
    return String(w).replace(/[\u064B-\u0652\u0640]/g, '').replace(/[^\u0600-\u06FF]/g, '');
  }
  function isFunc(w) {
    const s = coreWord(w);
    return FUNC.has(s) || s.length <= 2;
  }

  /* ---------- chunk building (pure function of timeline) ---------- */
  function buildChunks(segments) {
    const chunks = [];
    segments.forEach(seg => {
      const ws = seg.words;
      if (Array.isArray(seg.groups) && seg.groups.length) {
        // explicit group override (e.g. balanced end-card rhythm):
        // each group = 1-2 words joined by spaces, consumed in order
        let wi = 0;
        seg.groups.forEach(grp => {
          const toks = String(grp).trim().split(/\s+/);
          const grpWords = [];
          toks.forEach(tok => {
            const w = ws[wi];
            if (w && coreWord(w.w) === coreWord(tok)) { grpWords.push(w); wi++; }
          });
          if (grpWords.length) {
            chunks.push({ words: grpWords,
              start: Math.max(0, grpWords[0].t0 - 0.04),
              speechEnd: grpWords[grpWords.length - 1].t1 });
          }
        });
        // any unconsumed trailing words fall back to auto pairing
        while (wi < ws.length) {
          const w = ws[wi];
          chunks.push({ words: [w], start: Math.max(0, w.t0 - 0.04), speechEnd: w.t1 });
          wi++;
        }
        return;
      }
      let i = 0;
      while (i < ws.length) {
        let take = 1;
        if (i + 1 < ws.length) {
          const nxt = ws[i + 1];
          const pairDur = nxt.t1 - ws[i].t0;
          if (isFunc(ws[i].w)) take = 2;                                   // function word leads its complement
          else if (!isFunc(nxt.w) && pairDur <= 2.0) take = 2;             // natural pair
        }
        const grp = ws.slice(i, i + take);
        i += take;
        chunks.push({ words: grp, start: Math.max(0, grp[0].t0 - 0.04), speechEnd: grp[grp.length - 1].t1 });
      }
    });
    // window locking: end <= next.start (overlap impossible by construction)
    for (let j = 0; j < chunks.length; j++) {
      const c = chunks[j];
      const nxt = chunks[j + 1];
      if (!nxt) { c.end = c.speechEnd + 0.45; c.fade = 0.16; }
      else if (nxt.start - c.speechEnd > 0.12) {                       // silence gap after this chunk
        c.end = c.speechEnd + Math.min(0.45, (nxt.start - c.speechEnd) - 0.05);
        c.fade = 0.16;
      } else {                                                          // immediate successor → instant swap
        c.end = nxt.start; c.fade = 0;
      }
      if (c.end <= c.start) c.end = c.start + 0.2;
    }
    return chunks;
  }

  /* ---------- DOM (built once) ---------- */
  const S = { chunks: [], built: false };

  function init() {
    if (S.built) return;
    const TL = window.VE2_TIMELINE;
    S.chunks = buildChunks(TL.segments);
    const root = document.getElementById('caption-root');
    const NSel = document.createElementNS(NS, 'g');
    root.appendChild(NSel);

    S.chunks.forEach(c => {
      const g = document.createElementNS(NS, 'g');
      g.setAttribute('opacity', '0');
      NSel.appendChild(g);
      const text = document.createElementNS(NS, 'text');
      text.setAttribute('x', '540');
      text.setAttribute('y', String(BASE_Y));
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('font-size', String(FONT));
      text.setAttribute('font-weight', '700');
      text.setAttribute('class', 'ar');
      g.appendChild(text);
      const tspans = [];
      c.words.forEach((w, k) => {
        const ts = document.createElementNS(NS, 'tspan');
        ts.textContent = (k > 0 ? ' ' : '') + w.w;
        ts.setAttribute('fill', CREAM);
        text.appendChild(ts);
        tspans.push({ ts, t0: w.t0, t1: w.t1, gold: false });
      });
      c.g = g; c.text = text; c.tspans = tspans; c.capsule = null; c.fs = FONT;
    });

    // measure + capsule sizing (engine calls init only after fonts are ready)
    S.chunks.forEach(c => {
        let r1 = c.text.getBoundingClientRect();
        if (r1.width > MAX_W) {
          c.fs = Math.floor(FONT * MAX_W / r1.width);
          c.text.setAttribute('font-size', String(c.fs));
          r1 = c.text.getBoundingClientRect();
        }
        const padX = 34, padY = 17;
        const w = r1.width + padX * 2, h = r1.height + padY * 2;
        const yTop = Math.min(r1.top - padY, 1690 - h);
        const r = document.createElementNS(NS, 'rect');
        r.setAttribute('x', String(540 - w / 2));
        r.setAttribute('y', String(yTop));
        r.setAttribute('width', String(w));
        r.setAttribute('height', String(h));
        r.setAttribute('rx', String(h / 2));
        r.setAttribute('fill', '#0e0b14');
        r.setAttribute('fill-opacity', '0.80');
        r.setAttribute('stroke', GOLD);
        r.setAttribute('stroke-opacity', '0.38');
        r.setAttribute('stroke-width', '2.5');
        c.g.insertBefore(r, c.text);
        c.capsule = r;
    });
    S.built = true;
  }

  const ease = u => 1 - Math.pow(1 - Math.min(1, Math.max(0, u)), 3);

  /* ---------- deterministic per-frame update (dirty-checked writes) ---------- */
  function update(t) {
    if (!S.built) return;
    for (let j = 0; j < S.chunks.length; j++) {
      const c = S.chunks[j];
      let op = 0;
      if (t >= c.start && t < c.end) {
        if (c.fade > 0 && t > c.end - c.fade) op = (c.end - t) / c.fade;
        else op = 1;
      }
      const opS = op.toFixed(3);
      const popping = op > 0 && (t - c.start) < 0.15;   // pop-in scale window
      if (c.__op !== opS || popping) {
        c.__op = opS;
        c.g.setAttribute('opacity', opS);
        if (op > 0) {
          const since = t - c.start;
          const sc = (0.92 + 0.08 * ease(since / 0.14)).toFixed(4);
          c.g.setAttribute('transform', `translate(540 ${BASE_Y}) scale(${sc}) translate(-540 ${-BASE_Y})`);
        }
      }
      // active word color
      for (let k = 0; k < c.tspans.length; k++) {
        const ts = c.tspans[k];
        const active = t >= ts.t0 && t < ts.t1 + 0.3;
        if (active !== ts.gold) {
          ts.gold = active;
          ts.ts.setAttribute('fill', active ? GOLD : CREAM);
        }
      }
    }
  }

  /* verification helper: visible chunk count + visible word count at time t */
  function stateAt(t) {
    let chunks = 0, words = 0;
    S.chunks.forEach(c => {
      let op = 0;
      if (t >= c.start && t < c.end) op = (c.fade > 0 && t > c.end - c.fade) ? (c.end - t) / c.fade : 1;
      if (op > 0.5) { chunks++; words += c.words.length; }
    });
    return { chunks, words, total: S.chunks.length };
  }

  function chunksDebug(t, cb) {
    if (!S.built) return;
    S.chunks.forEach(c => { if (t >= c.start && t < c.end) cb(c); });
  }

  window.VE2Captions = { init, update, stateAt, buildChunks, _chunksDebug: chunksDebug };
})();
