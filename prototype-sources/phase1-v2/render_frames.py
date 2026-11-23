#!/usr/bin/env python3
"""VE2 frame renderer / verifier (Playwright + Chromium, deterministic).
Modes:
  --stills "1,24,40,45,55,59" --outdir DIR   : test stills
  --start N --end M --out DIR --workers K    : full frame render (frames f%05d.png)
  --verify                                   : programmatic layout assertions (getBoundingClientRect)
  --determinism                              : re-render same t twice, compare bytes
"""
import argparse, hashlib, json, os, sys, time
from multiprocessing import Process

# PHASE 5 STEP 2: VE2_SCENE_URL env override (default unchanged) lets the
# renderer run against an isolated scene dir for A/B regression verification.
SCENE = os.environ.get("VE2_SCENE_URL",
                       "file:///home/z/my-project/visual-engine-2/scene/scene.html")

VERIFY_JS = r"""
() => {
  const NS = 'http://www.w3.org/2000/svg';
  const clamp = (v,a,b)=>Math.min(b,Math.max(a,v));
  const out = {};
  const cam = t => { window.__ve2.renderAt(t); return window.__ve2.cameraAt(t); };
  const scr = (wx, wy, cx, cy, s) => [540+(wx-cx)*s, 960+(wy-cy)*s];
  const intersect = (a,b) => !(a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top);

  function machineRects(t) {
    const [cx,cy,s] = cam(t);
    const layer = document.getElementById('layer-machines-front');
    return window.VE2.machines.map(m => {
      const r = document.createElementNS(NS,'rect');
      r.setAttribute('x', m.x0); r.setAttribute('y', m.y0);
      r.setAttribute('width', m.x1-m.x0); r.setAttribute('height', m.y1-m.y0);
      layer.appendChild(r);
      const b = r.getBoundingClientRect();
      layer.removeChild(r);
      return {id: m.id, left: b.left, top: b.top, right: b.right, bottom: b.bottom};
    });
  }

  // ---------- 1) Fix 3: title vs machines at t=1.0 ----------
  {
    const rects = machineRects(1.0);
    const tb = document.getElementById('title-card').getBoundingClientRect();
    const hits = rects.filter(r => r.right > 0 && r.left < 1080 && intersect(tb, r));
    out.title = { rect: {l:tb.left,t:tb.top,r:tb.right,b:tb.bottom},
                  machinesVisible: rects.filter(r=>r.right>0&&r.left<1080).map(r=>r.id),
                  overlaps: hits.map(r=>r.id),
                  topThirdOK: tb.bottom < 640, pass: hits.length===0 && tb.bottom < 640 };
  }
  // ---------- 2) Fix 2: empty gap between tank and funnel at t=40 ----------
  {
    const [cx,cy,s] = cam(40.0);
    // gap = open air between pipe outer edge (2422) and funnel left wall (2600-6)
    const g0 = scr(window.VE2.G.TANK.x1 + 20, 440, cx,cy,s);
    const g1 = scr(window.VE2.G.FUNNEL.x0-6, 630, cx,cy,s);
    const gap = {left: Math.min(g0[0],g1[0]), top: Math.min(g0[1],g1[1]),
                 right: Math.max(g0[0],g1[0]), bottom: Math.max(g0[1],g1[1])};
    const intruders = [];
    // walk to LEAF paint nodes; groups' bboxes are unions (L-shaped pipe would false-positive)
    const effOpacity = node => { let o = 1, n = node; while (n && n.getAttribute) { const a = parseFloat(n.getAttribute('opacity') ?? '1'); o *= a; n = n.parentNode; } return o; };
    const clippedByPipe = node => { let n = node; while (n && n.getAttribute) { const cp = n.getAttribute('clip-path'); if (cp && cp.indexOf('pipeInteriorClip') !== -1) return true; n = n.parentNode; } return false; };
    ['layer-products','layer-products-back'].forEach(lid => {
      const leaves = document.getElementById(lid).querySelectorAll('path,rect,circle,ellipse,line,polygon,text');
      leaves.forEach(ch => {
        const op = effOpacity(ch);
        if (op < 0.05) return;
        if (clippedByPipe(ch)) return;  // paint mathematically confined to pipe interior
        const b = ch.getBoundingClientRect();
        if (b.width===0 && b.height===0) return;
        if (intersect(b, gap)) intruders.push({layer: lid, tag: ch.tagName, op: +op.toFixed(2)});
      });
    });
    const liq = document.getElementById('pipeLiquid');
    out.gap40 = { gap,
                  intruders,
                  pipeLiquidOpacity: (()=>{window.__ve2.renderAt(40.0); return liq.getAttribute('opacity');})(),
                  pass: intruders.length===0 };
  }
  // ---------- 3) Fix 4: end card text inside safe margins at t=59 ----------
  {
    window.__ve2.renderAt(59.0);
    const lines = [...document.querySelectorAll('#end-card text')].map(tx => {
      const b = tx.getBoundingClientRect();
      return {text: tx.textContent, left: b.left, right: b.right, top: b.top, bottom: b.bottom,
              ok: b.left >= 80 && b.right <= 1000};
    });
    out.endCard = { lines, pass: lines.every(l=>l.ok) };
  }
  // ---------- 4) Fix 1: single-pop at t=24 + capsule bounds ----------
  {
    window.__ve2.renderAt(24.0);
    const st = window.VE2Captions.stateAt(24.0);
    // measure visible capsule rect
    let capRect = null;
    window.VE2Captions._chunksDebug(24.0, c => {
      if (!capRect && c.capsule) { const b = c.capsule.getBoundingClientRect(); capRect = {l:b.left,t:b.top,r:b.right,b:b.bottom}; }
    });
    out.caption24 = { ...st, capRect, pass: st.chunks<=1 && st.words<=2 };
    // sweep whole timeline: never more than 2 words on screen
    let worst = {t:0, words:0, chunks:0};
    for (let tt=0.2; tt<=60.5; tt+=0.25) {
      const s2 = window.VE2Captions.stateAt(tt);
      if (s2.words > worst.words) worst = {t:tt, words:s2.words, chunks:s2.chunks};
    }
    out.captionSweep = { worst, pass: worst.words<=2 };
  }
  // ---------- 5) Fix 5a: bar level through tunnel exit (WORLD coords) ----------
  {
    const samples = [54.7, 55.0, 55.3, 55.6];
    const bars = samples.map(tt => {
      const [cx,cy,s] = cam(tt);
      window.__ve2.renderAt(tt);
      const fill = window.VE2.els.molds[1].fill; // mold 2: tunnel exit ~55s
      const b = fill.getBoundingClientRect();
      const wTop = (b.top-960)/s + cy, wBot = (b.bottom-960)/s + cy;
      const wH = b.height/s, wL = (b.left-540)/s + cx;
      return {t: tt, wL: +wL.toFixed(1), wTop: +wTop.toFixed(1), wBot: +wBot.toFixed(1), wH: +wH.toFixed(1)};
    });
    const hDelta = Math.max(...bars.map(b=>b.wH)) - Math.min(...bars.map(b=>b.wH));
    const bDelta = Math.max(...bars.map(b=>b.wBot)) - Math.min(...bars.map(b=>b.wBot));
    out.tunnelExit = { samples: bars, hDelta: +hDelta.toFixed(2), bDelta: +bDelta.toFixed(2),
                       pass: hDelta <= 2.0 && bDelta <= 2.0 };
  }
  // ---------- 5b) Fix 5b: hero bar smooth entrance ----------
  {
    const probe = tt => { window.__ve2.renderAt(tt);
      const g = document.getElementById('hero-bar');
      return {t: tt, op: parseFloat(g.getAttribute('opacity')), tr: g.getAttribute('transform')};
    };
    const seq = [55.8, 56.1, 56.25, 56.5].map(probe);
    const opOK = seq[0].op < 0.02 && seq[3].op > 0.95 && seq[2].op > seq[1].op && seq[1].op > seq[0].op;
    out.heroEntrance = { seq: seq.map(x=>({t:x.t,op:+x.op.toFixed(3)})), pass: opOK };
  }
  // ---------- 6) Fix 6: funnel + tunnel banners (PHASE 5 STEP 2: expected
  // labels come from window.VE2_PRODUCT.world; fallback keeps the legacy
  // chocolate strings for scenes without product-data.js) ----------
  {
    window.__ve2.renderAt(56.5);
    const banners = [...document.querySelectorAll('.ve2-banner')].map(g => {
      const tx = g.querySelector('text');
      const b = tx.getBoundingClientRect();
      return {text: tx.textContent, left: b.left, top: b.top, right: b.right, bottom: b.bottom,
              visible: b.right>0 && b.left<1080 && b.bottom>0 && b.top<1920};
    });
    const lb = (window.VE2_PRODUCT && window.VE2_PRODUCT.world
                && window.VE2_PRODUCT.world.layer_banners) || [];
    const labelOf = key => { const w = lb.find(x => x.key === key); return w ? w.label_ar : (key==='FUNNEL' ? 'الصب في القوالب' : 'نفق التبريد'); };
    const hasFunnel = banners.some(b=>b.text===labelOf('FUNNEL') && b.visible);
    const hasTunnel = banners.some(b=>b.text===labelOf('TUNNEL') && b.visible);
    out.banners = { banners, pass: hasFunnel && hasTunnel };
  }
  // ---------- 7) chips: label must not touch the number bean ----------
  {
    let worst = null;
    window.VE2.els.chipGroups.forEach((cg, idx) => {
      const label = cg.g.querySelectorAll('text')[0];
      const bean = cg.g.querySelector('g');
      const lb = label.getBoundingClientRect();
      const bb = bean.getBoundingClientRect();
      const gap = bb.left - lb.right;
      if (worst === null || gap < worst.gap) worst = {idx, gap: +gap.toFixed(2)};
    });
    out.chips = { worst, pass: worst.gap >= 5 };
  }
  // ---------- 8) Phase 2: mold schedule non-overlap under the deposition spout ----------
  {
    let worst = {t: 0, inZone: 0, pouring: 0};
    for (let tt = 44.0; tt <= 54.4; tt += 0.05) {
      window.__ve2.renderAt(tt);
      let inZone = 0, pouring = 0;
      window.VE2.els.molds.forEach(mo => {
        if (parseFloat(mo.shellG.getAttribute('opacity')) > 0.5) {
          const tr = mo.shellG.getAttribute('transform') || '';
          const m2 = /translate\(([-\d.]+) /.exec(tr);
          if (m2) { const x = parseFloat(m2[1]); if (x >= 2640 && x <= 2760) inZone++; }
        }
      });
      window.VE2.els.threads.forEach(th => {
        if (parseFloat(th.getAttribute('opacity')) > 0.5) pouring++;
      });
      if (inZone > worst.inZone || pouring > worst.pouring) worst = {t: +tt.toFixed(2), inZone, pouring};
    }
    out.moldOverlap = { worst, pass: worst.inZone <= 1 && worst.pouring <= 1 };
  }
  // ---------- 9) Phase 2: mixing-machine inlet cleanliness at 37s/42s ----------
  // Nothing from the product layers may paint ABOVE the tank roof inside the
  // tank span; steam must be structurally clipped inside the tank interior.
  {
    const effOpacity = node => { let o = 1, n = node; while (n && n.getAttribute) { const a = parseFloat(n.getAttribute('opacity') ?? '1'); o *= a; n = n.parentNode; } return o; };
    const clippedIn = (node, clipName) => { let n = node; while (n && n.getAttribute) { const cp = n.getAttribute('clip-path'); if (cp && cp.indexOf(clipName) !== -1) return true; n = n.parentNode; } return false; };
    const checks = [37.5, 42.0].map(tt => {
      const [cx,cy,s] = cam(tt);
      const T = window.VE2.G.TANK;
      const z0 = scr(T.x0, T.y0 - 60, cx, cy, s);
      const z1 = scr(T.x1, T.y0 - 1, cx, cy, s);
      const zone = {left: Math.min(z0[0],z1[0]), top: Math.min(z0[1],z1[1]),
                    right: Math.max(z0[0],z1[0]), bottom: Math.max(z0[1],z1[1])};
      const intruders = [];
      ['layer-products','layer-products-back'].forEach(lid => {
        const leaves = document.getElementById(lid).querySelectorAll('path,rect,circle,ellipse,line,polygon,text');
        leaves.forEach(ch => {
          const op = effOpacity(ch);
          if (op < 0.05) return;
          if (clippedIn(ch, 'pipeInteriorClip') || clippedIn(ch, 'tankSteamClip') || clippedIn(ch, 'tankEntryClip')) return;
          const b = ch.getBoundingClientRect();
          if (b.width===0 && b.height===0) return;
          const over = !(b.right < zone.left || zone.right < b.left || b.bottom < zone.top || zone.bottom < b.top);
          if (over) intruders.push({layer: lid, tag: ch.tagName, op: +op.toFixed(2)});
        });
      });
      return {t: tt, intruders};
    });
    const steamOK = (() => {
      const S2 = window.VE2.els.steam;
      if (!S2 || S2.length < 3) return false;
      const r = document.getElementById('tankSteamRect');
      if (!r || parseFloat(r.getAttribute('y')) < window.VE2.G.TANK.y0) return false;
      let n = S2[0].g.parentNode, ok = false;
      while (n && n.getAttribute) {
        const cp = n.getAttribute('clip-path');
        if (cp && cp.indexOf('tankSteamClip') !== -1) { ok = true; break; }
        n = n.parentNode;
      }
      return ok;
    })();
    const totalIntr = checks.reduce((a,c)=>a+c.intruders.length,0);
    out.inletClean = { checks, steamOK, totalIntruders: totalIntr, pass: totalIntr === 0 && steamOK };
  }
  return out;
}
"""

def make_page(browser):
    ctx = browser.new_context(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    page = ctx.new_page()
    page.goto(SCENE)
    page.wait_for_function("window.__ve2Ready === true", timeout=30000)
    return ctx, page

def mode_stills(times, outdir):
    from playwright.sync_api import sync_playwright
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-device-scale-factor=1"])
        ctx, page = make_page(b)
        for t in times:
            page.evaluate(f"window.__ve2.renderAt({t})")
            path = os.path.join(outdir, f"t{str(t).replace('.','_')}.png")
            page.screenshot(path=path)
            print("still", t, "->", path)
        b.close()

def mode_verify():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-device-scale-factor=1"])
        ctx, page = make_page(b)
        res = page.evaluate(VERIFY_JS)
        print(json.dumps(res, ensure_ascii=False, indent=1))
        ok = all(v.get("pass") for v in res.values() if isinstance(v, dict) and "pass" in v)
        print("VERIFY_RESULT:", "PASS" if ok else "FAIL")
        b.close()
        sys.exit(0 if ok else 2)

def render_chunk(worker, start, end, outdir):
    from playwright.sync_api import sync_playwright
    os.makedirs(outdir, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-device-scale-factor=1"])
        ctx, page = make_page(b)
        t0 = time.time()
        for n in range(start, end + 1):
            t = n / 30.0
            page.evaluate(f"window.__ve2.renderAt({t:.6f})")
            page.screenshot(path=os.path.join(outdir, f"f{n:05d}.png"))
            if (n - start) % 200 == 0:
                el = time.time() - t0
                print(f"[w{worker}] {n}/{end} ({(n-start+1)/(el+1e-9):.1f} fps)", flush=True)
        b.close()

def mode_range(start, end, outdir, workers):
    total = end - start + 1
    per = (total + workers - 1) // workers
    procs = []
    for w in range(workers):
        s = start + w * per
        e = min(start + w * per + per - 1, end)
        if s > e: break
        pr = Process(target=render_chunk, args=(w, s, e, outdir))
        pr.start(); procs.append(pr)
    for pr in procs: pr.join()

def mode_determinism():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--force-device-scale-factor=1"])
        ctx, page = make_page(b)
        ok = True
        for t in (25.0, 40.0, 59.0):
            h = []
            for rep in range(2):
                page.evaluate(f"window.__ve2.renderAt({t})")
                page.evaluate(f"window.__ve2.renderAt({t})")
                data = page.screenshot()
                h.append(hashlib.sha256(data).hexdigest()[:16])
            same = h[0] == h[1]
            ok = ok and same
            print(f"determinism t={t}: {h[0]} vs {h[1]} -> {'SAME' if same else 'DIFF'}")
        print("DETERMINISM:", "PASS" if ok else "FAIL")
        b.close()
        sys.exit(0 if ok else 2)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stills"); ap.add_argument("--outdir", default="analysis/stills")
    ap.add_argument("--start", type=int); ap.add_argument("--end", type=int)
    ap.add_argument("--out", default="frames"); ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--verify", action="store_true"); ap.add_argument("--determinism", action="store_true")
    a = ap.parse_args()
    if a.verify: mode_verify()
    elif a.determinism: mode_determinism()
    elif a.stills: mode_stills([float(x) for x in a.stills.split(",")], a.outdir)
    elif a.start is not None: mode_range(a.start, a.end, a.out, a.workers)
    else: print("nothing to do")
