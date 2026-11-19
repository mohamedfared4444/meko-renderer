#!/usr/bin/env python3
"""VE2 Phase 4 — tightened narration pacing + deterministic factory SFX.

PART A (pacing): re-place seg1..seg7 on the frozen 60.633 s timeline.
  - Enzo raw FLACs are kept NATURAL (no pause surgery) except seg5/seg7,
    whose scene windows are tight (internal pauses capped, then gentle
    atempo only if still overflowing).
  - Scene-anchored optimizer: crisp post-cut resumes, pre-cut quiet
    buffers >= 0.35 s at every scene cut, uniform scene-breath gaps.
  - Word timings recomputed from the ACTUAL final audio (RMS envelope ->
    speech bursts -> char-share boundaries snapped to real gaps).

PART B (SFX): 100% deterministic procedural factory sound design.
  - numpy-only synthesis, single seeded RandomState (fixed seed) for any
    noise; every oscillator phase is a fixed formula. No Math.random(),
    no external assets, no copyrighted material.
  - SFX families: conveyor hum (scene 1 + molding line), roasting drum
    warmth (tumbler + burner + crackle), roller grinder purr, conching
    swirl, chocolate pour stream, cooling tunnel cold air + chimes.
  - Mix targets: narration speech mean ~ -16.5 dB, music pad -35 dB,
    SFX bus ~ -32 dB, AAC decoded true peak <= -1.4 dBFS, zero clipping.

Outputs: download/ve2-audio-timeline.json (+ timeline.js rebuild),
         output/audio/narration_mix_phase4.m4a, verify report JSON.
"""
import json
import math
import os
import subprocess
import sys

import numpy as np

ROOT = "/home/z/my-project/visual-engine-2"
SRC = os.path.join(ROOT, "download/ve2-narration-enzo")
AUD = os.path.join(ROOT, "output/audio")
DL = "/home/z/my-project/download"
DLB = os.path.join(ROOT, "download")
SR = 48000
VIDEO_DUR = 1819 / 30.0  # 60.63333...

SPEECH_TH_DB = -45.0
MIN_BURST = 0.08
GAP_MIN = 0.14
SNAP = 0.18
ATEMP_MIN, ATEMP_MAX = 1.02, 1.06

# scene cuts (frozen visual timeline)
CUTS = {"scene2": 14.35, "scene3": 24.85, "scene4": 36.90,
        "scene5": 44.17, "scene6": 54.40, "scene7": 55.90}

# frozen narration anchors (kept from the approved Phase-2 design)
S5_ANCHOR = 37.15          # conching narration starts 0.25 s after cut3
POST5 = 0.26               # seg7 resumes 0.26 s after the demold cut
LEAD = 1.60                # cinematic open before seg1
G12 = 0.72                 # within-scene gap seg1 -> seg2

# per-segment internal-pause policy: None = keep Enzo natural
PAUSE_KEEP = {"seg1": None, "seg2": None, "seg3": None, "seg4": None,
              "seg5": 0.22, "seg6": None, "seg7": 0.24}

SEG7_GROUPS = ["وبكده الألواح", "بتطلع جاهزة", "من حبة", "كاكاو",
               "لقطعة", "شوكولاتة"]

# deterministic SFX seed (fixed forever — byte-identical mixes)
SFX_SEED = 987126


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def load_flac_mono(path):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le",
                        "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    return np.frombuffer(r.stdout, dtype=np.float32).copy()


def save_wav(path, a, ch=1, fmt="f32"):
    codec = "flac" if path.lower().endswith(".flac") else \
        ("pcm_f32le" if fmt == "f32" else "pcm_s16le")
    data = a.astype(np.float32).tobytes()
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "f32le",
                          "-ar", str(SR), "-ac", str(ch), "-i", "-",
                          "-c:a", codec, path],
                         stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                         stderr=subprocess.PIPE)
    _, err = p.communicate(data)
    if p.returncode != 0:
        print("wav save fail:", err.decode()[:200]); sys.exit(2)


def env_db(a, win=480, hop=240):
    """Moving RMS in dB — O(n) via cumulative sum (identical math to a
    box-filter convolution, but ~100x faster on 60 s of audio)."""
    x = np.asarray(a, dtype=np.float64)
    if len(x) < win:
        return np.array([-120.0])
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    idx = np.arange(0, len(x) - win + 1, hop)
    s = c[idx + win] - c[idx]
    e = np.sqrt(s / win)
    return 20 * np.log10(e + 1e-9)


def speech_runs(a):
    d = env_db(a)
    ts = np.arange(len(d)) * 240 / SR
    speech = d > SPEECH_TH_DB
    runs = []
    i = 0
    while i < len(speech):
        if speech[i]:
            j = i
            while j + 1 < len(speech) and speech[j + 1]:
                j += 1
            t0, t1 = ts[i], ts[min(j + 1, len(ts) - 1)] + 480 / SR
            if t1 - t0 >= MIN_BURST:
                runs.append([t0, min(t1, len(a) / SR)])
            i = j + 1
        else:
            i += 1
    merged = []
    for r in runs:
        if merged and r[0] - merged[-1][1] < GAP_MIN:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return merged


def tighten_pauses(a, max_pause):
    """Shrink internal silences longer than max_pause down to max_pause."""
    d = env_db(a)
    speech = d > SPEECH_TH_DB
    sil = []
    i = 0
    while i < len(speech):
        if not speech[i]:
            j = i
            while j + 1 < len(speech) and not speech[j + 1]:
                j += 1
            s0, s1 = i * 240, min((j + 1) * 240 + 480, len(a))
            if i > 0 and j + 1 < len(speech):
                sil.append((s0, s1))
            i = j + 1
        else:
            i += 1
    out = []
    pos = 0
    removed = 0.0
    for s0, s1 in sil:
        dur = (s1 - s0) / SR
        if dur > max_pause:
            keep_end = s0 + int(max_pause * SR)
            out.append(a[pos:keep_end])
            removed += dur - max_pause
            pos = s1
    out.append(a[pos:])
    if not out:
        return a, 0.0
    return np.concatenate(out), removed


def trim_edges(a, pad=0.08):
    """Trim leading/trailing silence to speech +- pad (anti-clip guard)."""
    runs = speech_runs(a)
    if not runs:
        return a, 0.0, 0.0
    t0, t1 = runs[0][0], runs[-1][1]
    i0 = max(0, int((t0 - pad) * SR))
    i1 = min(len(a), int((t1 + pad) * SR))
    return a[i0:i1].copy(), t0, len(a) / SR - t1


def atempo_file(src, dst, factor):
    r = run(["ffmpeg", "-y", "-v", "error", "-i", src, "-filter:a",
             f"atempo={factor:.4f}", "-c:a", "flac", dst])
    if r.returncode != 0:
        print("atempo fail:", r.stderr[:200]); sys.exit(2)


def word_timings(a, words):
    runs = speech_runs(a)
    if not runs:
        return None
    t_start, t_end = runs[0][0], runs[-1][1]
    gaps = [(runs[i][1] + runs[i + 1][0]) / 2 for i in range(len(runs) - 1)
            if runs[i + 1][0] - runs[i][1] >= 0.10]
    d = env_db(a)
    ts = np.arange(len(d)) * 240 / SR
    inside = d <= SPEECH_TH_DB + 3
    j = 0
    while j < len(inside):
        if inside[j]:
            k = j
            while k + 1 < len(inside) and inside[k + 1]:
                k += 1
            g0, g1 = ts[j], ts[min(k + 1, len(ts) - 1)]
            if t_start < (g0 + g1) / 2 < t_end and 0.05 <= g1 - g0 <= 0.45:
                gaps.append((g0 + g1) / 2)
            j = k + 1
        else:
            j += 1
    gaps = sorted(set(round(g, 3) for g in gaps))
    chars = [max(len(w), 1) for w, _ in words]
    total = sum(chars)
    n = len(words)
    bounds = [t_start]
    acc = 0
    for i in range(n - 1):
        acc += chars[i]
        raw = t_start + (t_end - t_start) * acc / total
        if gaps:
            g = min(gaps, key=lambda x: abs(x - raw))
            if abs(g - raw) <= SNAP:
                raw = g
        bounds.append(raw)
    bounds.append(t_end)
    out = []
    for i, (w, _) in enumerate(words):
        out.append({"w": w, "t0": round(bounds[i], 3),
                    "t1": round(bounds[i + 1], 3)})
    return out


def compress(x, sr=SR, threshold_db=-17.0, ratio=2.5,
             attack_ms=8.0, release_ms=200.0):
    blk = max(1, int(sr * 0.001))
    nblk = len(x) // blk
    if nblk < 4:
        return x
    rms = np.sqrt((x[:nblk * blk].astype(np.float64) ** 2)
                  .reshape(nblk, blk).mean(axis=1))
    env_db = 20 * np.log10(rms + 1e-9)
    over = env_db > threshold_db
    target_db = np.where(over, threshold_db + (env_db - threshold_db) / ratio,
                         env_db)
    gr = target_db - env_db
    aa = math.exp(-1.0 / (sr * attack_ms / 1000.0 / blk))
    rr = math.exp(-1.0 / (sr * release_ms / 1000.0 / blk))
    g = np.empty(nblk)
    cur = 0.0
    for i in range(nblk):
        k = aa if gr[i] < cur else rr
        cur = k * cur + (1 - k) * gr[i]
        g[i] = cur
    gf = np.repeat(10 ** (g / 20), blk)
    if len(gf) < len(x):
        gf = np.concatenate([gf, np.ones(len(x) - len(gf))])
    return x * gf


def peak_limiter(x, ceiling=0.794, sr=SR, lookahead_ms=3.0, release_ms=120.0):
    blk = max(1, int(sr * 0.001))
    nblk = len(x) // blk
    if nblk < 4:
        return np.clip(x, -ceiling, ceiling)
    a = np.abs(x[:nblk * blk]).reshape(nblk, blk).max(axis=1)
    la = max(1, int(lookahead_ms))
    env = a.copy()
    for k in range(1, la + 1):
        env[:-k] = np.maximum(env[:-k], a[k:])
    need = np.where(env > ceiling, ceiling / np.maximum(env, 1e-9), 1.0)
    ra = math.exp(-1.0 / (sr * release_ms / 1000.0 / blk))
    g = np.empty(nblk)
    cur = 1.0
    for i in range(nblk):
        cur = need[i] if need[i] < cur else ra * cur + (1 - ra) * need[i]
        g[i] = cur
    gf = np.repeat(g, blk)
    if len(gf) < len(x):
        gf = np.concatenate([gf, np.ones(len(x) - len(gf))])
    return x * gf


def volumedetect(path, ss=None, to=None):
    cmd = ["ffmpeg", "-v", "info"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    cmd += ["-i", path]
    if to is not None:
        if ss is not None:
            cmd += ["-t", str(round(to - ss, 3))]
        else:
            cmd += ["-to", str(to)]
    cmd += ["-af", "volumedetect", "-f", "null", "-"]
    r = run(cmd)
    mv = mx = None
    for ln in r.stderr.splitlines():
        if "mean_volume:" in ln:
            mv = float(ln.split("mean_volume:")[1].split("dB")[0])
        if "max_volume:" in ln:
            mx = float(ln.split("max_volume:")[1].split("dB")[0])
    return mv, mx


# ======================================================================
# PART B — deterministic procedural SFX engine
# ======================================================================
def band_noise(rng, n, lo, hi, sr=SR):
    """Gaussian white noise band-limited to [lo, hi] Hz via FFT masking."""
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1.0 / sr)
    mask = (f >= lo) & (f <= hi)
    X[~mask] = 0
    return np.fft.irfft(X, n).astype(np.float64)


def window_env(n_total, spans, fade=0.45, sr=SR):
    """Raised-cosine on/off envelope for a list of (t0, t1) spans."""
    t = np.arange(n_total) / sr
    env = np.zeros(n_total)
    for t0, t1 in spans:
        m = (t >= t0) & (t <= t1)
        e = np.zeros(n_total)
        e[m] = 1.0
        # smooth fades at span edges
        r = np.clip((t - t0) / fade, 0, 1)
        f = np.clip((t1 - t) / fade, 0, 1)
        e = np.minimum(e, r) * np.minimum(e, f)
        env = np.maximum(env, e)
    return env


def sinus(freq, n, phase=0.0, sr=SR):
    return np.sin(2 * np.pi * freq * np.arange(n) / sr + phase)


def build_sfx():
    """Factory/process SFX bus, stereo, exactly VIDEO_DUR long.
    Fully deterministic: one seeded RandomState + fixed formulas."""
    rng = np.random.RandomState(SFX_SEED)
    n_total = int(round(VIDEO_DUR * SR))
    t = np.arange(n_total) / SR
    L = np.zeros(n_total)
    R = np.zeros(n_total)

    def add(sig, spans, pan=0.0):
        """Mix sig (mono, full length) into L/R inside spans w/ fades."""
        nonlocal L, R
        e = window_env(n_total, spans)
        L += sig * e * (1.0 - max(0.0, pan))
        R += sig * e * (1.0 + min(0.0, pan))

    # ---- 1) conveyor hum: scene 1 belt (0-14.35) + molding line (44.17-54.4)
    hum_spans = [(0.05, CUTS["scene2"]), (CUTS["scene5"], CUTS["scene6"])]
    hum = 0.55 * sinus(55.0, n_total, 0.3) + 0.30 * sinus(110.0, n_total, 1.1)
    rumble = band_noise(rng, n_total, 40, 120)
    hum += 0.9 * rumble
    am = 0.75 + 0.25 * sinus(0.5, n_total, 0.0)          # slow belt surge
    roller_t = np.zeros(n_total)                          # roller ticks
    tick_period = 0.36
    k = np.arange(1, int(VIDEO_DUR / tick_period))
    for tk in k * tick_period:
        i0 = int(tk * SR)
        ln = int(0.018 * SR)
        if i0 + ln < n_total:
            tt = np.arange(ln) / SR
            roller_t[i0:i0 + ln] += np.sin(2 * np.pi * 1900 * tt) * \
                np.exp(-tt * 320)
    hum = (hum + 0.16 * roller_t) * am
    add(hum, hum_spans, pan=0.0)

    # ---- 2) roasting drum warmth (scene 2: 14.35-24.85)
    burn = band_noise(rng, n_total, 120, 350)
    burn *= 0.8 + 0.2 * sinus(0.35, n_total, 0.7)         # burner breathing
    drum_th = np.zeros(n_total)                           # tumbler thumps
    rot_period = 1.25
    for tk in np.arange(14.6, CUTS["scene3"], rot_period):
        i0 = int(tk * SR)
        ln = int(0.30 * SR)
        if i0 + ln < n_total:
            tt = np.arange(ln) / SR
            drum_th[i0:i0 + ln] += np.sin(2 * np.pi * 70 * tt * (1 + 0.04 * tt)) * \
                np.exp(-tt * 12) * 0.9
    crackle = np.zeros(n_total)                           # bean crackle ticks
    n_cr = int((CUTS["scene3"] - CUTS["scene2"]) * 3.2)
    for tc in np.sort(rng.uniform(CUTS["scene2"] + 0.3, CUTS["scene3"] - 0.2,
                                  n_cr)):
        i0 = int(tc * SR)
        ln = int(0.012 * SR)
        if i0 + ln < n_total:
            tt = np.arange(ln) / SR
            fc = rng.uniform(1500, 3200)
            crackle[i0:i0 + ln] += np.sin(2 * np.pi * fc * tt) * \
                np.exp(-tt * 500) * rng.uniform(0.4, 1.0)
    roast = burn + drum_th + 0.10 * crackle
    add(roast, [(CUTS["scene2"] + 0.05, CUTS["scene3"] - 0.15)], pan=0.08)

    # ---- 3) roller grinder purr (scene 3: 24.85-36.9)
    gear = np.zeros(n_total)
    for hk in range(1, 7):                                # harmonic stack
        gear += (1.0 / hk) * sinus(65.0 * hk, n_total, 0.21 * hk)
    am_g = 0.62 + 0.38 * (0.5 + 0.5 * sinus(4.6, n_total, 0.0))**1.5
    mech = band_noise(rng, n_total, 250, 700)
    mech *= 0.7 + 0.3 * sinus(2.3, n_total, 1.9)
    grind = (gear + 0.55 * mech) * am_g
    add(grind, [(CUTS["scene3"] + 0.05, CUTS["scene4"] - 0.15)], pan=-0.07)

    # ---- 4) conching swirl (scene 4: 36.9-44.17)
    swirl_n = band_noise(rng, n_total, 300, 900)
    # slow spectral wobble via AM at 0.18 Hz + vibrato tone
    swirl = swirl_n * (0.72 + 0.28 * sinus(0.18, n_total, 0.5))
    liq = sinus(180.0, n_total, 1.2) * (0.5 + 0.5 * sinus(0.45, n_total, 0.0))
    liq += 0.35 * sinus(181.8, n_total, 0.4)              # gentle beating
    conch = swirl + 0.22 * liq
    add(conch, [(CUTS["scene4"] + 0.05, CUTS["scene5"] - 0.12)], pan=0.05)

    # ---- 5) chocolate pour stream (molding/depositing: 44.4-52.6)
    pour_n = band_noise(rng, n_total, 1200, 3500)
    pour_rhythm = 0.55 + 0.45 * (0.5 + 0.5 * sinus(0.8, n_total, 0.9))**1.3
    drip = np.zeros(n_total)                              # tiny drip accents
    n_dr = 26
    for td in np.sort(rng.uniform(44.8, 52.4, n_dr)):
        i0 = int(td * SR)
        ln = int(0.010 * SR)
        if i0 + ln < n_total:
            tt = np.arange(ln) / SR
            drip[i0:i0 + ln] += np.sin(2 * np.pi * 2400 * tt) * \
                np.exp(-tt * 700) * 0.8
    pour = (pour_n * pour_rhythm + 0.12 * drip)
    add(pour, [(44.40, 52.60)], pan=-0.04)

    # ---- 6) cooling tunnel cold air + chimes (48.5-54.4) + exit whoosh
    cold = band_noise(rng, n_total, 2500, 6000)
    cold *= 0.7 + 0.3 * sinus(0.22, n_total, 1.4)
    add(cold, [(48.50, CUTS["scene6"] - 0.10)], pan=0.06)
    chime = np.zeros(n_total)
    for tc, fc in ((48.9, 1568.0), (51.2, 2093.0), (53.4, 1568.0)):
        i0 = int(tc * SR)
        ln = int(0.9 * SR)
        if i0 + ln < n_total:
            tt = np.arange(ln) / SR
            chime[i0:i0 + ln] += np.sin(2 * np.pi * fc * tt) * \
                np.exp(-tt * 4.5) * 0.9
    add(chime, [(48.5, CUTS["scene6"])], pan=0.0)
    exit_w = band_noise(rng, n_total, 400, 1600)
    t0w, t1w = CUTS["scene6"] + 0.05, CUTS["scene6"] + 0.75
    win = np.zeros(n_total)
    i0, i1 = int(t0w * SR), int(t1w * SR)
    win[i0:i1] = np.hanning(max(1, i1 - i0))
    add(exit_w * win, [(t0w, t1w)], pan=0.0)

    return np.stack([L, R], axis=1)


def normalize_db(a_stereo, target_db):
    """Scale stereo bus so its OVERALL mean RMS hits target_db."""
    rms = math.sqrt(float(np.mean(a_stereo.astype(np.float64) ** 2)))
    cur = 20 * math.log10(rms + 1e-9)
    g = target_db - cur
    return a_stereo * (10 ** (g / 20)), cur, g


# ======================================================================
def main():
    os.makedirs(AUD, exist_ok=True)
    rep = json.load(open(os.path.join(SRC, "segments_report.json")))
    texts = {s["id"]: s["text"] for s in rep["segments"]}
    order = [s["id"] for s in rep["segments"]]

    report = {"phase": 4, "windows": [], "processing": [], "placements": [],
              "gaps": [], "verify": {}}

    # ---------- 1) load + per-segment processing ----------
    finals = {}
    for sid in order:
        a = load_flac_mono(os.path.join(SRC, f"{sid}_Enzo.flac"))
        raw_dur = len(a) / SR
        note = {"id": sid, "raw_dur": round(raw_dur, 3)}
        a, lead_s, trail_s = trim_edges(a, pad=0.08)
        note["edge_trim"] = [round(lead_s, 3), round(trail_s, 3)]
        keep = PAUSE_KEEP[sid]
        if keep is not None:
            a, removed = tighten_pauses(a, keep)
            note["pause_keep"] = keep
            note["pause_removed"] = round(removed, 3)
        dur = len(a) / SR
        note["processed_dur"] = round(dur, 3)
        finals[sid] = a
        report["processing"].append(note)
        print(f"[load] {sid}: raw={raw_dur:.3f} -> processed={dur:.3f} "
              f"(keep={keep})")

    d = {sid: len(finals[sid]) / SR for sid in order}
    d1, d2, d3, d4, d5, d6, d7 = (d["seg1"], d["seg2"], d["seg3"], d["seg4"],
                                  d["seg5"], d["seg6"], d["seg7"])

    # ---------- 2) scene-anchored placement optimizer ----------
    S1 = CUTS["scene2"] - d1 - d2                    # scene-1 air pool
    S2 = CUTS["scene3"] - CUTS["scene2"] - d3        # scene-2 air pool
    S3 = CUTS["scene4"] - CUTS["scene3"] - d4        # scene-3 air pool
    S4 = CUTS["scene5"] - CUTS["scene4"] - d5        # scene-4 air pool
    S5 = CUTS["scene6"] - CUTS["scene5"] - d6        # scene-5 air pool
    tail1 = S1 - LEAD - G12
    assert tail1 >= 0.35, f"tail1 too small: {tail1:.3f}"

    # seg5 fit inside scene 4 (post3 = S4_ANCHOR - cut4, pre4' >= 0.35)
    post3 = round(S5_ANCHOR - CUTS["scene4"], 3)
    pre4 = round(CUTS["scene5"] - S5_ANCHOR - d5, 3)
    if pre4 < 0.35:
        print(f"seg5 window overflow (pre4'={pre4:.3f}) -> atempo fallback")
        allowed = CUTS["scene5"] - S5_ANCHOR - 0.35
        factor = max(ATEMP_MIN, min(ATEMP_MAX, d5 / allowed))
        tmp = os.path.join(AUD, "seg5_tmp.flac")
        save_wav(tmp, finals["seg5"])
        atempo_file(tmp, os.path.join(AUD, "seg5_final.flac"), factor)
        os.unlink(tmp)
        finals["seg5"] = load_flac_mono(os.path.join(AUD, "seg5_final.flac"))
        d5 = len(finals["seg5"]) / SR
        S4 = CUTS["scene5"] - CUTS["scene4"] - d5
        pre4 = round(CUTS["scene5"] - S5_ANCHOR - d5, 3)
        report["processing"][4]["atempo"] = round(factor, 4)
        report["processing"][4]["processed_dur"] = round(d5, 3)

    # uniform scene-breath target across gaps 23/34/45
    T345 = tail1 + S2 + S3 + post3
    u3 = T345 / 3.0
    post1 = max(0.35, min(1.20, u3 - tail1))
    pre2 = S2 - post1
    post2 = (S3 + post3 - S2 + post1) / 2.0
    pre3 = S3 - post2

    # gaps 56/67 balanced
    u2 = (pre4 + S5 + POST5) / 2.0
    post4 = max(0.35, min(2.00, u2 - pre4))
    pre5 = S5 - post4

    s = {
        "seg1": round(LEAD, 3),
        "seg2": round(LEAD + d1 + G12, 3),
        "seg3": round(CUTS["scene2"] + post1, 3),
        "seg4": round(CUTS["scene3"] + post2, 3),
        "seg5": round(S5_ANCHOR, 3),
        "seg6": round(CUTS["scene5"] + post4, 3),
        "seg7": round(CUTS["scene6"] + POST5, 3),
    }
    e = {sid: round(s[sid] + d[sid], 3) for sid in order}
    assert e["seg7"] <= 60.6333 - 0.30, \
        f"seg7 overruns: e7={e['seg7']:.3f}"
    # safety: pre-cut buffers at every scene cut
    for cut, prev, nxt in ((CUTS["scene2"], "seg2", "seg3"),
                           (CUTS["scene3"], "seg3", "seg4"),
                           (CUTS["scene4"], "seg4", "seg5"),
                           (CUTS["scene5"], "seg5", "seg6"),
                           (CUTS["scene6"], "seg6", "seg7")):
        pre_buf = cut - e[prev]
        assert pre_buf >= 0.35, f"pre-cut buffer {prev}->{cut}: {pre_buf:.3f}"
        post_buf = s[nxt] - cut
        assert post_buf >= 0.20, f"post-cut resume {cut}->{nxt}: {post_buf:.3f}"

    SCENES = [
        {"name": "01 title over production line + raw cocoa beans conveyor",
         "start": 0.0, "end": CUTS["scene2"]},
        {"name": "02 roasting drum cutaway", "start": CUTS["scene2"],
         "end": CUTS["scene3"]},
        {"name": "03 grinding into cocoa paste (steel rollers cutaway)",
         "start": CUTS["scene3"], "end": CUTS["scene4"]},
        {"name": "04 smooth liquid chocolate (conching tank)",
         "start": CUTS["scene4"], "end": CUTS["scene5"]},
        {"name": "05 molding & cooling", "start": CUTS["scene5"],
         "end": 54.4},
        {"name": "06 demolding pullback", "start": 54.4, "end": 55.9},
        {"name": "07 final wide reveal (bean to bar)", "start": 55.9,
         "end": 60.6333},
    ]

    print("[placements]")
    for sid in order:
        print(f"  {sid}: {s[sid]:.3f} -> {e[sid]:.3f} (d={d[sid]:.3f})")
    gaps_calc = {}
    for a_id, b_id in zip(order, order[1:]):
        gaps_calc[f"{a_id}->{b_id}"] = round(s[b_id] - e[a_id], 3)
    gaps_calc["lead_in"] = s["seg1"]
    gaps_calc["tail_out"] = round(60.6333 - e["seg7"], 3)
    print("[gaps]", json.dumps(gaps_calc))
    report["placements"] = [{"id": sid, "start": s[sid], "end": e[sid],
                             "dur": round(d[sid], 3)} for sid in order]
    report["gaps"] = gaps_calc

    # ---------- 3) word timings from the real final audio ----------
    segments = []
    words_total = 0
    for sid in order:
        text = texts[sid]
        toks = text.replace("،", " ،").split()
        toks = [t for t in toks if t != "،"] or [text]
        a = finals[sid]
        wt = word_timings(a, [(t, 0) for t in toks])
        if wt is None:
            print("no speech bursts for", sid); sys.exit(3)
        for w in wt:
            w["t0"] = round(s[sid] + w["t0"], 3)
            w["t1"] = round(s[sid] + w["t1"], 3)
        words_total += len(wt)
        seg = {"id": sid, "text": text, "placement": s[sid],
               "ends_at": e[sid], "words": wt}
        if sid == "seg7":
            seg["groups"] = SEG7_GROUPS
        segments.append(seg)

    timeline = {
        "video": {"duration": 60.6333, "fps": 30, "frames": 1819,
                  "width": 1080, "height": 1920},
        "scenes": SCENES,
        "segments": segments,
    }
    for p in (DL, DLB):
        with open(os.path.join(p, "ve2-audio-timeline.json"), "w",
                  encoding="utf-8") as f:
            json.dump(timeline, f, ensure_ascii=False, indent=2)
    print(f"[timeline] {len(segments)} segments, {words_total} words "
          f"-> ve2-audio-timeline.json (x2 locations)")

    # rebuild scene/timeline.js with groups passthrough
    bt = open(os.path.join(ROOT, "prototype/build_timeline.py")).read()
    bt = bt.replace(
        '"words": [{"w": w["w"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3)} for w in s["words"]],',
        '"words": [{"w": w["w"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3)} for w in s["words"]],\n        **({"groups": s["groups"]} if s.get("groups") else {}),')
    g = {"__name__": "__main__"}
    exec(compile(bt, "build_timeline_inline", "exec"), g)
    os.system(f"cp {ROOT}/scene/timeline.js {ROOT}/prototype/timeline.js")

    # ---------- 4) music pad (deterministic, identical to Phase 2) ----------
    n_total = int(VIDEO_DUR * SR)
    chords = [
        [87.31, 174.61, 220.00, 261.63],   # F
        [65.41, 130.81, 164.81, 196.00],   # C
        [73.42, 146.83, 174.61, 220.00],   # Dm
        [58.27, 116.54, 146.83, 174.61],   # Bb
    ]
    chord_len = VIDEO_DUR / 4
    tL = np.zeros(n_total, dtype=np.float64)
    tR = np.zeros(n_total, dtype=np.float64)
    tt = np.arange(n_total) / SR
    for ci, freqs in enumerate(chords):
        c0, c1 = ci * chord_len, min((ci + 1) * chord_len + 1.0, VIDEO_DUR)
        i0, i1 = int(c0 * SR), int(c1 * SR)
        seg_t = tt[i0:i1]
        env = np.ones(len(seg_t))
        atk = 0.8; rel = 1.0
        env = np.minimum(np.minimum((seg_t - c0) / atk, (c1 - seg_t) / rel), 1.0)
        env = np.clip(env, 0, 1)
        for vi, f in enumerate(freqs):
            amp = 0.5 / (vi + 1)
            ph = ci * 1.7 + vi * 0.9
            tL[i0:i1] += amp * env * (
                np.sin(2 * np.pi * f * seg_t + ph)
                + 0.35 * np.sin(2 * np.pi * 2 * f * seg_t + ph * 1.3)
                + 0.12 * np.sin(2 * np.pi * 3 * f * seg_t + ph * 0.7))
            tR[i0:i1] += amp * env * (
                np.sin(2 * np.pi * f * 1.0015 * seg_t + ph + 0.35)
                + 0.35 * np.sin(2 * np.pi * 2 * f * 1.0015 * seg_t + ph * 1.3)
                + 0.12 * np.sin(2 * np.pi * 3 * f * 1.0015 * seg_t + ph * 0.7))
    trem = 1.0 + 0.10 * np.sin(2 * np.pi * 0.25 * tt)
    tL *= trem; tR *= trem
    fade_in = np.clip(tt / 1.5, 0, 1)
    fade_out = np.clip((VIDEO_DUR - tt) / 2.5, 0, 1)
    tL *= fade_in * fade_out; tR *= fade_in * fade_out
    mx = max(np.abs(tL).max(), np.abs(tR).max())
    tL = tL / mx * 0.5; tR = tR / mx * 0.5
    music = np.stack([tL, tR], axis=1).astype(np.float32)
    save_wav(os.path.join(AUD, "music_pad_raw.wav"), music.ravel(), ch=2)
    print("[music] pad generated (F-C-Dm-Bb, deterministic)")

    # ---------- 5) SFX bus (deterministic) ----------
    sfx = build_sfx()
    save_wav(os.path.join(AUD, "sfx_bus_raw.wav"), sfx.ravel(), ch=2)
    sfx_n, sfx_cur, sfx_gain = normalize_db(sfx, -32.0)
    save_wav(os.path.join(AUD, "sfx_bus.wav"), sfx_n.ravel(), ch=2)
    print(f"[sfx] bus raw mean={sfx_cur:.1f}dB gain={sfx_gain:+.2f}dB "
          f"-> -32.0 dB target (seed={SFX_SEED})")
    report["verify"]["sfx_raw_mean_db"] = round(sfx_cur, 2)
    report["verify"]["sfx_gain_db"] = round(sfx_gain, 2)
    report["verify"]["sfx_seed"] = SFX_SEED

    # ---------- 6) narration track + level staging ----------
    nar = np.zeros(n_total, dtype=np.float64)
    for sid in order:
        a = finals[sid]
        i0 = int(s[sid] * SR)
        i1 = min(i0 + len(a), n_total)
        nar[i0:i1] += a[:i1 - i0]
    save_wav(os.path.join(AUD, "narration_raw.wav"), nar.astype(np.float32))

    nar_f = nar.astype(np.float64)
    sp_mask = np.zeros(n_total, dtype=bool)
    for r0, r1 in speech_runs(nar_f):
        sp_mask[int(r0 * SR):int(r1 * SR)] = True
    if sp_mask.sum() < SR:
        sp_mask[:] = True
    rms_sp = math.sqrt(float(np.mean(nar_f[sp_mask] ** 2)))
    cur_sp = 20 * math.log10(rms_sp + 1e-9)
    gain_n = -16.0 - cur_sp

    mm = math.sqrt(float(np.mean(music.astype(np.float64) ** 2)))
    cur_m = 20 * math.log10(mm + 1e-9)
    gain_m = -35.0 - cur_m
    print(f"[levels] speech mean={cur_sp:.1f}dB gain={gain_n:+.2f}dB | "
          f"music mean={cur_m:.1f}dB gain={gain_m:+.2f}dB")

    gn0 = 10 ** (gain_n / 20)
    x = gn0 * nar_f
    for _ in range(5):
        x = compress(x, threshold_db=-19.0, ratio=3.0)
        x = peak_limiter(x, ceiling=0.794)
        r = math.sqrt(float(np.mean(x[sp_mask] ** 2)))
        x = x * (10 ** ((-16.5 - 20 * math.log10(r + 1e-9)) / 20))
    nar_lim = peak_limiter(x, ceiling=0.794)
    rms3 = math.sqrt(float(np.mean(nar_lim[sp_mask] ** 2)))
    pk_l = 20 * math.log10(float(np.abs(nar_lim).max()) + 1e-9)
    nar_mean_db = 20 * math.log10(rms3 + 1e-9)
    print(f"[levels] limited speech mean={nar_mean_db:.2f}dB peak={pk_l:.2f}dBFS")
    report["verify"]["narration_limited_speech_mean_db"] = round(nar_mean_db, 2)
    report["verify"]["narration_limited_peak_dbfs"] = round(pk_l, 2)
    report["verify"]["music_gain_db"] = round(gain_m, 2)
    if not (-18.0 <= nar_mean_db <= -16.0):
        print("!! narration speech mean out of spec [-18, -16]"); sys.exit(6)

    gm = 10 ** (gain_m / 20)
    gs = 10 ** ((-32.0 - sfx_cur) / 20)
    mixL = nar_lim + gm * tL + gs * sfx_n[:, 0]
    mixR = nar_lim + gm * tR + gs * sfx_n[:, 1]
    peak = max(float(np.abs(mixL).max()), float(np.abs(mixR).max()))
    pk_db = 20 * math.log10(peak + 1e-9)
    report["verify"]["mix_peak_dbfs"] = round(pk_db, 2)
    if peak > 0.85:
        k = 0.85 / peak
        mixL *= k; mixR *= k
        report["verify"]["peak_guard_scale"] = round(k, 4)
    print(f"[levels] mix peak={pk_db:.2f}dBFS "
          f"(guard {report['verify'].get('peak_guard_scale', 1.0)})")

    st = np.stack([mixL, mixR], axis=1).astype(np.float32)
    save_wav(os.path.join(AUD, "mix_final_phase4.wav"), st.ravel(), ch=2,
             fmt="f32")

    # ---------- 7) iterative AAC encode, decoded peak pinned <= -1.30 dBFS
    # (native AAC overshoot is non-monotonic w.r.t. small input scaling, so
    #  accept any decoded peak <= -1.30 immediately and otherwise try a small
    #  deterministic ladder of pre-scales, keeping the closest to -1.45)
    scale_db = 0.0
    dec_peak = None
    best = None  # (abs(peak - (-1.45)) subject to peak <= -1.30, scale, peak)
    ladder = [0.0, -0.12, -0.30, -0.55, -0.85]
    for it, cand in enumerate(ladder, 1):
        if cand != 0.0:
            sg = 10 ** (cand / 20)
            st2 = np.stack([mixL * sg, mixR * sg], axis=1).astype(np.float32)
            save_wav(os.path.join(AUD, "mix_final_phase4.wav"), st2.ravel(),
                     ch=2, fmt="f32")
        r = run(["ffmpeg", "-y", "-v", "error",
                 "-i", os.path.join(AUD, "mix_final_phase4.wav"),
                 "-c:a", "aac", "-b:a", "192k",
                 os.path.join(AUD, "narration_mix_phase4.m4a")])
        if r.returncode != 0:
            print("mix fail:", r.stderr[:300]); sys.exit(4)
        pr = run(["ffmpeg", "-v", "info", "-i",
                  os.path.join(AUD, "narration_mix_phase4.m4a"),
                  "-af", "astats=metadata=1:reset=0", "-f", "null", "-"])
        pk = [float(l.split("Peak level dB:")[1]) for l in
              pr.stderr.splitlines() if "Peak level dB" in l]
        dec_peak = max(pk) if pk else -99
        print(f"[aac] pass {it} (scale {cand:+.2f} dB): "
              f"decoded peak={dec_peak:.2f}dBFS")
        if dec_peak <= -1.30:
            best = (abs(dec_peak + 1.45), cand, dec_peak)
            break
        # keep the best safe candidate so far (no clipping, deepest OK)
        if dec_peak <= -1.00 and (best is None or
                                  abs(dec_peak + 1.45) < best[0]):
            best = (abs(dec_peak + 1.45), cand, dec_peak)
        scale_db = cand
    if best is None:
        print("!! no safe AAC candidate found"); sys.exit(7)
    _, scale_db, dec_peak = best
    if scale_db != ladder[-1] or True:
        # deterministically re-encode the chosen candidate
        sg = 10 ** (scale_db / 20)
        st2 = np.stack([mixL * sg, mixR * sg], axis=1).astype(np.float32)
        save_wav(os.path.join(AUD, "mix_final_phase4.wav"), st2.ravel(),
                 ch=2, fmt="f32")
        r = run(["ffmpeg", "-y", "-v", "error",
                 "-i", os.path.join(AUD, "mix_final_phase4.wav"),
                 "-c:a", "aac", "-b:a", "192k",
                 os.path.join(AUD, "narration_mix_phase4.m4a")])
        if r.returncode != 0:
            print("mix fail:", r.stderr[:300]); sys.exit(4)
    report["verify"]["aac_scale_db"] = round(scale_db, 2)
    report["verify"]["aac_decoded_peak_dbfs"] = round(dec_peak, 2)
    if dec_peak > -1.0:
        print("!! decoded peak not safely below 0 dBFS"); sys.exit(7)
    print("[mix] narration_mix_phase4.m4a written")

    # ---------- 8) verification ----------
    dur_r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0",
                 os.path.join(AUD, "narration_mix_phase4.m4a")])
    mix_dur = float(dur_r.stdout.strip())
    mv, mxv = volumedetect(os.path.join(AUD, "narration_mix_phase4.m4a"))
    checks = {"mix_duration": round(mix_dur, 3), "mix_mean_db": mv,
              "mix_max_db": mxv}
    print(f"[verify] mix dur={mix_dur:.3f}s mean={mv:.1f}dB max={mxv:.1f}dB")
    if abs(mix_dur - VIDEO_DUR) > 0.05:
        print("!! mix duration mismatch"); sys.exit(8)

    windows = [
        ("speech", s["seg1"] + 0.3, e["seg1"] - 0.3),
        ("ambient", e["seg1"] + 0.1, s["seg2"] - 0.1),
        ("speech", s["seg3"] + 0.5, e["seg3"] - 0.5),
        ("speech", s["seg4"] + 0.5, e["seg4"] - 0.5),
        ("ambient", e["seg4"] + 0.2, CUTS["scene4"] - 0.2),
        ("speech", s["seg5"] + 0.3, e["seg5"] - 0.3),
        ("speech", s["seg6"] + 0.3, e["seg6"] - 0.3),
        ("ambient", e["seg6"] + 0.2, s["seg7"] - 0.2),
        ("ambient", 0.05, s["seg1"] - 0.1),
        ("speech", s["seg7"] + 0.3, e["seg7"] - 0.3),
    ]
    wres = []
    for kind, a1, a2 in windows:
        if a2 - a1 < 0.15:
            continue
        mv2, mx2 = volumedetect(os.path.join(AUD, "narration_mix_phase4.m4a"),
                                a1, a2)
        wres.append({"kind": kind, "win": [round(a1, 2), round(a2, 2)],
                     "mean_db": mv2, "max_db": mx2})
        print(f"[verify] {kind} {a1:.2f}-{a2:.2f}: mean={mv2:.1f}dB "
              f"max={mx2:.1f}dB")
    checks["windows"] = wres

    # boundary gaps from the real narration speech mask
    gaps = []
    bounds = [(CUTS["scene2"], "cut1 scene2 start"),
              (CUTS["scene3"], "cut2 scene3 start"),
              (CUTS["scene4"], "cut3 scene4 start"),
              (CUTS["scene5"], "cut4 scene5 start"),
              (CUTS["scene6"], "cut5 scene6 start"),
              (60.633, "video end")]
    runs_all = sorted(speech_runs(nar_f))
    for b, label in bounds:
        prev_end = 0.0
        next_start = None
        for r0, r1 in runs_all:
            if r0 >= b - 1e-6:
                next_start = r0
                break
            prev_end = max(prev_end, min(r1, b))
        gap = b - prev_end
        entry = {"at": b, "label": label,
                 "last_speech_end": round(prev_end, 3),
                 "gap_s": round(gap, 3), "ok": bool(gap >= 0.35)}
        if next_start is not None:
            entry["next_speech_start"] = round(next_start, 3)
            entry["resume_after_cut"] = round(next_start - b, 3)
        gaps.append(entry)
        print(f"[gap] {label}: last speech ends {prev_end:.2f} -> "
              f"gap {gap:.2f}s {'OK' if gap >= 0.35 else 'FAIL'}")
    checks["boundary_gaps"] = gaps

    # inter-segment speech gaps (exact, from mask)
    seg_gaps = []
    for a_id, b_id in zip(order, order[1:]):
        seg_gaps.append({"from": a_id, "to": b_id,
                         "gap_s": round(s[b_id] - e[a_id], 3)})
    checks["segment_gaps"] = seg_gaps
    # overlap check: speech runs must be disjoint
    overlaps = []
    for i in range(len(runs_all) - 1):
        if runs_all[i + 1][0] < runs_all[i][1] - 1e-4:
            overlaps.append(runs_all[i])
    checks["speech_overlaps"] = overlaps
    report["verify"].update(checks)

    for p, name in ((DL, "ve2-phase4-audio-verify.json"),
                    (DLB, "ve2-phase4-audio-verify.json")):
        with open(os.path.join(p, name), "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    ok_all = (all(g_["ok"] for g_ in gaps) and not overlaps)
    print("AUDIO_BUILD_OK" if ok_all else "AUDIO_BUILD_WITH_WARNINGS")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
