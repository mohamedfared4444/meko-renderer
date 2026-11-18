#!/usr/bin/env python3
"""Smoke test: load scene, catch console/page errors, sanity-check init."""
import json, sys
from playwright.sync_api import sync_playwright

SCENE = "file:///home/z/my-project/visual-engine-2/scene/scene.html"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--force-device-scale-factor=1"])
    page = b.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    errs, msgs = [], []
    page.on("pageerror", lambda e: errs.append(getattr(e, "stack", None) or str(e)))
    page.on("console", lambda m: msgs.append(f"{m.type}: {m.text}") if m.type in ("error", "warning") else None)
    page.goto(SCENE)
    try:
        page.wait_for_function("window.__ve2Ready === true", timeout=15000)
    except Exception:
        print("!! init not ready — dumping errors")
        print("PAGE_ERRORS:", json.dumps(errs))
        print("CONSOLE:", json.dumps(msgs[:12]))
        flag = page.evaluate("() => ({ready: !!window.__ve2Ready, hasVE2: !!window.VE2, hasCap: !!window.VE2Captions, hasAnim: !!window.__ve2, fonts: document.fonts ? document.fonts.status : 'n/a'})")
        print("STATE:", json.dumps(flag))
        b.close(); sys.exit(1)
    info = page.evaluate("""() => ({
        banners: document.querySelectorAll('.ve2-banner').length,
        chunks: window.VE2_TIMELINE.segments.reduce((a,s)=>a+s.words.length,0),
        machines: window.VE2.machines.map(m=>m.id),
        moldClips: ['A','B','C'].every(k => !!document.getElementById('moldFillClip'+k)),
        capChunks: (()=>{let n=0; window.VE2Captions._chunksDebug(-1, ()=>n++); return document.querySelectorAll('#caption-root g').length;})()
    })""")
    page.evaluate("window.__ve2.renderAt(25.0)")
    print("PAGE_ERRORS:", json.dumps(errs))
    print("CONSOLE:", json.dumps(msgs[:8]))
    print("INFO:", json.dumps(info, ensure_ascii=False))
    b.close()
    sys.exit(1 if errs else 0)
