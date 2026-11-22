#!/usr/bin/env python3
"""VE2 Phase 4 — tightened narration pacing + deterministic factory SFX.

PHASE 4.2 (music pad removal, user-reported "هششش / TV-switch" fix):
  After the Phase-4.1 SFX removal the user STILL heard a soft "هششش"
  / TV channel-switch / TV-off artifact between narration lines. With
  the SFX bus already digital silence, the only remaining non-speech
  source was the warm ambient music pad: its chord-boundary envelope
  ramps (1.0 s release every ~15.16 s), tremolo and 2.5 s end fade can
  read as a faint "TV cut" under quiet gaps. MUSIC_ENABLED = False now
  mutes the pad entirely (bus gain exactly 0.0): the mix is PURE Enzo
  narration with clean 20 ms raised-cosine micro-fades at every
  segment edge and EXACT digital silence between lines. Segment
  placements, word timings, ve2-audio-timeline.json, timeline.js and
  the 2.5D frames are untouched (md5-verified).

PHASE 4.1 (SFX removal, user-reported "نغمشة" fix):
  The user reported an unpleasant crackly/hissy/ticking noise after
  speech / between lines. Root cause = the procedural SFX bus (roller
  ticks, bean crackle, drip accents, band-noise hisses/swirls, chime
  pings, exit whoosh). ALL SFX layers are now DISABLED (SFX_ENABLED =
  False): the mix is narration + the warm deterministic ambient music
  pad only, digitally free of crackle/hiss/ticks. Segment placements,
  word timings, timeline.js, and the 2.5D frames are untouched.

PART A (pacing): re-place seg1..seg7 on the frozen 60.633 s timeline.
  - Enzo raw FLACs are kept NATURAL (no pause surgery) except seg5/seg7,
    whose scene windows are tight (internal pauses capped, then gentle
    atempo only if still overflowing).
  - Scene-anchored optimizer: crisp post-cut resumes, pre-cut quiet
    buffers >= 0.35 s at every scene cut, uniform scene-breath gaps.
  - Word timings recomputed from the ACTUAL final audio (RMS envelope ->
    speech bursts -> char-share boundaries snapped to real gaps).

PART B (SFX): DISABLED in Phase 4.1 (kept for reference/history).
  - The full procedural factory SFX design (conveyor hum, roasting
    drum, roller grinder, conching swirl, pour stream, cooling tunnel)
    generated band-noise hiss + tick/crackle transients that the user
    heard as "نغمشة" between narration lines. Removed per user request.
  - Mix targets: narration speech mean ~ -16.5 dB, music pad -35 dB,
    AAC decoded true peak <= -1.4 dBFS, zero clipping.

Outputs: download/ve2-audio-timeline.json (+ timeline.js rebuild),
         output/audio/narration_mix_phase4.m4a, verify report JSON.
"""
import json
import math
import os
import shutil
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

# PHASE 4.1: procedural SFX bus disabled (user-reported "نغمشة" —
# crackly/hissy/ticking residue between narration lines). When False,
# build_sfx() is never called and the SFX bus is DIGITAL SILENCE, so the
# mix is exactly narration + warm ambient music pad. Flip to True only
# if a future pass redesigns the SFX from the ground up.
SFX_ENABLED = False

# PHASE 4.2: ambient music pad disabled (user still heard a soft
# "هششش" / TV channel-switch / TV-off artifact between narration lines
# even after the SFX removal). With the SFX bus already digital
# silence, the only remaining non-speech source was the warm pad: its
# chord-boundary envelope ramps (1.0 s release every ~15.16 s), tremolo
# and 2.5 s end fade can read as a faint "TV cut" under quiet gaps.
# When False the pad gain is exactly 0.0 in the mix: PURE Enzo
# narration with clean 20 ms raised-cosine micro-fades at every
# segment edge and EXACT digital silence between lines. Flip to True
# only if a future pass redesigns the pad with gap-safe envelopes.
MUSIC_ENABLED = False

# PHASE 4.2: micro-fade length (raised cosine) at every segment edge,
# applied on the MIX BUS ONLY (never on finals[...], so word timings,
# placements and the timeline JSON stay byte-identical).
MICRO_FADE_S = 0.020


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
    """DISABLED in Phase 4.1 (user-reported "نغمشة").

    The Phase-4 procedural factory SFX bus (conveyor hum + roller ticks,
    roasting burner hiss + tumbler thumps + bean crackle, roller-grinder
    gear/mechanical band-noise, conching swirl, pour stream + drip
    accents, cooling-tunnel cold air + chimes + exit whoosh) produced
    band-limited noise and high-frequency tick transients that the user
    heard as an unpleasant crackly/hissy layer between narration lines.

    Every harsh layer has been REMOVED from this builder. The bus now
    returns DIGITAL SILENCE so the final mix contains exactly:
        narration (Enzo)  +  warm deterministic ambient music pad.
    Deterministic by construction (exact zeros, no RNG draw at all).
    """
    n_total = int(round(VIDEO_DUR * SR))
    return np.zeros((n_total, 2), dtype=np.float64)


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

    report = {"phase": 4, "sub_phase": "4.2", "windows": [],
              "processing": [], "placements": [],
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
    print("[music] pad generated (F-C-Dm-Bb, deterministic) — "
          + ("active in mix" if MUSIC_ENABLED else
             "MUTED in mix (phase 4.2: MUSIC_ENABLED=False)"))

    # ---------- 5) SFX bus (DISABLED in Phase 4.1 — "نغمشة" fix) ----------
    # No procedural SFX at all: the bus is digital silence, so the mix is
    # exactly narration + warm ambient music pad (zero crackle/hiss/ticks).
    if SFX_ENABLED:
        sfx = build_sfx()               # returns digital silence anyway
        save_wav(os.path.join(AUD, "sfx_bus_raw.wav"), sfx.ravel(), ch=2)
        sfx_n, sfx_cur, sfx_gain = normalize_db(sfx, -32.0)
        save_wav(os.path.join(AUD, "sfx_bus.wav"), sfx_n.ravel(), ch=2)
        report["verify"]["sfx_raw_mean_db"] = round(sfx_cur, 2)
        report["verify"]["sfx_gain_db"] = round(sfx_gain, 2)
    else:
        sfx_n = np.zeros((n_total, 2), dtype=np.float64)
        sfx_cur = -120.0
        sfx_gain = 0.0
        print("[sfx] DISABLED (phase 4.1): crackle/drip/tick/hiss/swirl "
              "layers removed — mix = narration + warm pad only")
    report["verify"]["sfx_enabled"] = bool(SFX_ENABLED)
    report["verify"]["sfx_seed"] = SFX_SEED
    report["verify"]["sfx_note"] = (
        "phase 4.1: procedural SFX removed per user report of crackly "
        "hiss/tick (\u0646\u063a\u0645\u0634\u0629) between narration lines; "
        "bus = digital silence")

    # ---------- 6) narration track + level staging ----------
    # PHASE 4.2: 20 ms raised-cosine micro-fades at every segment edge.
    # Applied to the MIX BUS ONLY (finals[...] untouched), so word
    # timings, placements and ve2-audio-timeline.json stay byte-identical.
    nf = int(MICRO_FADE_S * SR)
    ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(nf) / nf))
    nar = np.zeros(n_total, dtype=np.float64)
    for sid in order:
        a = finals[sid]
        i0 = int(s[sid] * SR)
        i1 = min(i0 + len(a), n_total)
        seg = a[:i1 - i0].astype(np.float64).copy()
        if len(seg) > 2 * nf:
            seg[:nf] *= ramp
            seg[-nf:] *= ramp[::-1]
        nar[i0:i1] += seg
    save_wav(os.path.join(AUD, "narration_raw.wav"), nar.astype(np.float32))
    print(f"[nar] {len(order)} segments placed, "
          f"{int(MICRO_FADE_S * 1000)} ms raised-cosine micro-fades at "
          f"every edge (mix bus only)")

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
          f"music mean={cur_m:.1f}dB gain={gain_m:+.2f}dB"
          + ("" if MUSIC_ENABLED else "  (music MUTED — not applied)"))

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
    report["verify"]["music_enabled"] = bool(MUSIC_ENABLED)
    report["verify"]["music_gain_db"] = (round(gain_m, 2) if MUSIC_ENABLED
                                         else 0.0)
    report["verify"]["music_note"] = (
        "phase 4.2: ambient music pad muted per user report of a soft "
        "\u0647\u0634\u0634\u0634 / TV-switch artifact between "
        "narration lines; mix = pure narration, gaps = digital silence")
    if not (-18.0 <= nar_mean_db <= -16.0):
        print("!! narration speech mean out of spec [-18, -16]"); sys.exit(6)

    # PHASE 4.2: muted buses contribute EXACTLY 0.0, so the mix is
    # bit-identical to the limited narration bus and gap samples stay
    # digital zero (0.0 * finite = 0.0 exactly in IEEE-754).
    gm = 10 ** (gain_m / 20) if MUSIC_ENABLED else 0.0
    gs = 10 ** ((-32.0 - sfx_cur) / 20) if SFX_ENABLED else 0.0
    mixL = nar_lim + gm * tL + gs * sfx_n[:, 0]
    mixR = nar_lim + gm * tR + gs * sfx_n[:, 1]
    if not MUSIC_ENABLED and not SFX_ENABLED:
        print("[mix] PURE NARRATION (music + sfx buses = exact 0.0)")
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

    # ---------- 7) iterative AAC encode, decoded peak pinned in
    # [-1.90, -1.30] dBFS (target ~ -1.45; phase 4.2 tightened check).
    # Native AAC overshoot is strongly non-monotonic w.r.t. small input
    # scaling (measured on the pure-narration mix: -0.12 dB -> -1.14 dBFS
    # but -0.30 dB -> -2.13 dBFS), so a deterministic ladder of pre-scales
    # is tried and the candidate whose decoded peak is closest to -1.45
    # dBFS while staying <= -1.30 dBFS wins (=> zero clipping by
    # construction). Falls back to a candidate in (-1.30, -1.00] only if
    # no in-window candidate exists. Each candidate is encoded to its own
    # file; the winner is BYTE-COPIED to narration_mix_phase4.m4a (no
    # re-encode step -> faster and guaranteed identical to the measured
    # candidate).
    ladder = [0.0, -0.12, -0.18, -0.24, -0.30, -0.55]
    ladder_res = []
    best_safe = None      # (dist, scale, peak, path) with peak <= -1.30 dBFS
    best_fb = None        # (dist, scale, peak, path) peak in (-1.30, -1.00]
    for it, cand in enumerate(ladder, 1):
        sg = 10 ** (cand / 20)
        st2 = np.stack([mixL * sg, mixR * sg], axis=1).astype(np.float32)
        cpath = os.path.join(AUD, f"aac_cand_{it}.m4a")
        save_wav(os.path.join(AUD, "mix_final_phase4.wav"), st2.ravel(),
                 ch=2, fmt="f32")
        r = run(["ffmpeg", "-y", "-v", "error",
                 "-i", os.path.join(AUD, "mix_final_phase4.wav"),
                 "-c:a", "aac", "-b:a", "192k", cpath])
        if r.returncode != 0:
            print("mix fail:", r.stderr[:300]); sys.exit(4)
        pr = run(["ffmpeg", "-v", "info", "-i", cpath,
                  "-af", "astats=metadata=1:reset=0", "-f", "null", "-"])
        pk = [float(l.split("Peak level dB:")[1]) for l in
              pr.stderr.splitlines() if "Peak level dB" in l]
        dec_peak = max(pk) if pk else -99
        ladder_res.append({"scale_db": cand,
                           "decoded_peak_dbfs": round(dec_peak, 2)})
        print(f"[aac] pass {it} (scale {cand:+.2f} dB): "
              f"decoded peak={dec_peak:.2f}dBFS")
        dist = abs(dec_peak + 1.45)
        if dec_peak <= -1.30:
            if best_safe is None or dist < best_safe[0]:
                best_safe = (dist, cand, dec_peak, cpath)
        elif dec_peak <= -1.00:
            if best_fb is None or dist < best_fb[0]:
                best_fb = (dist, cand, dec_peak, cpath)
    if best_safe is not None:
        _, scale_db, dec_peak, cpath = best_safe
    elif best_fb is not None:
        _, scale_db, dec_peak, cpath = best_fb
    else:
        print("!! no safe AAC candidate found"); sys.exit(7)
    shutil.copyfile(cpath, os.path.join(AUD, "narration_mix_phase4.m4a"))
    for it_ in range(1, len(ladder) + 1):
        p_ = os.path.join(AUD, f"aac_cand_{it_}.m4a")
        if os.path.exists(p_) and p_ != cpath:
            os.remove(p_)
    report["verify"]["aac_scale_db"] = round(scale_db, 2)
    report["verify"]["aac_decoded_peak_dbfs"] = round(dec_peak, 2)
    report["verify"]["aac_ladder"] = ladder_res
    report["verify"]["aac_target_window_dbfs"] = [-1.90, -1.30]
    report["verify"]["aac_peak_in_target"] = bool(-1.90 <= dec_peak <= -1.30)
    report["verify"]["aac_zero_clipping"] = bool(dec_peak <= -1.30)
    if dec_peak > -1.0:
        print("!! decoded peak not safely below 0 dBFS"); sys.exit(7)
    if not report["verify"]["aac_peak_in_target"]:
        print("!! decoded peak outside phase-4.2 target window "
              "[-1.90, -1.30] dBFS")
    print(f"[mix] narration_mix_phase4.m4a written "
          f"(scale {scale_db:+.2f} dB, decoded peak {dec_peak:.2f} dBFS)")

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

    # PHASE 4.1 — zero-crackle/hiss/tick proof (numpy FFT band analysis).
    # The removed SFX layers all lived above 1.5 kHz (roller ticks ~1.9
    # kHz, bean crackle 1.5-3.2 kHz, drips 2.4 kHz, pour hiss 1.2-3.5
    # kHz, cold-air hiss 2.5-6 kHz, chimes 1.6/2.1 kHz); the warm music
    # pad tops out near 785 Hz, so the 1.5k-19k "SFX zone" must be empty
    # in every narration-gap window. Hann-weighted rFFT per window; no
    # filter cold-start transients (the old ffmpeg-highpass check was
    # unreliable for that reason).
    # TRUE per-channel decode. A mono downmix must NOT be used for peak
    # checks: libswresample's stereo->mono matrix applies a 0.7071
    # coefficient per channel, so correlated L/R peaks are inflated by up
    # to +3.01 dB (this produced a bogus 1.106 abs-max on the first 4.2
    # run while the file's true per-channel peak was -2.13 dBFS).
    def decode_f32_stereo(path):
        rr = subprocess.run(["ffmpeg", "-v", "error", "-i", path,
                             "-f", "f32le", "-ar", str(SR), "-"],
                            capture_output=True)
        x = np.frombuffer(rr.stdout, dtype=np.float32).astype(np.float64)
        return x.reshape(-1, 2)

    def band_max_db(x, lo=1500.0, hi=19000.0):
        n = len(x)
        if n < 1024:
            return None
        X = np.abs(np.fft.rfft(x * np.hanning(n))) / max(1, n // 2)
        f = np.fft.rfftfreq(n, 1.0 / SR)
        m = (f >= lo) & (f <= hi)
        if not m.any():
            return None
        return 20 * math.log10(float(X[m].max()) + 1e-12)

    m4a_st = decode_f32_stereo(os.path.join(AUD,
                                            "narration_mix_phase4.m4a"))
    wav_st = decode_f32_stereo(os.path.join(AUD, "mix_final_phase4.wav"))
    m4a_pcm = m4a_st.mean(axis=1)   # (L+R)/2: peaks can only shrink
    wav_pcm = wav_st.mean(axis=1)
    gap_hf = []
    hf_ok = True
    for kind, a1, a2 in windows:
        if kind != "ambient" or a2 - a1 < 0.15:
            continue
        sl = slice(int(a1 * SR), int(a2 * SR))
        d_db = band_max_db(m4a_pcm[sl])
        w_db = band_max_db(wav_pcm[sl])
        ok = (d_db is not None and w_db is not None
              and d_db <= -100.0 and w_db <= -100.0)
        hf_ok = hf_ok and ok
        gap_hf.append({"win": [round(a1, 2), round(a2, 2)],
                       "sfx_zone_1.5k_19k_max_db": {
                           "decoded_m4a": round(d_db, 1),
                           "preencode_wav": round(w_db, 1)},
                       "ok": bool(ok)})
        print(f"[hf-check] gap {a1:.2f}-{a2:.2f}: 1.5-19k max "
              f"decoded={d_db:.1f}dB pre-encode={w_db:.1f}dB " +
              ("OK (no crackle/hiss/ticks)" if ok else "FAIL"))
    checks["gap_hf_check"] = gap_hf
    checks["gap_hf_ok"] = bool(hf_ok)

    # PHASE 4.2 — EXACT digital-silence proof between narration lines.
    # With SFX (4.1) and the ambient music pad (4.2) disabled, every
    # narration gap must be MATHEMATICALLY ZERO in the pre-encode WAV
    # (pure narration bus) and at the AAC codec noise floor in the
    # decoded m4a. Windows start 0.10 s after each segment end and end
    # 0.10 s before the next start so the +-0.08 s trim pads (possible
    # TTS room-tone tails) are excluded from the zero-assertion.
    sil_windows = [("lead_in", 0.05, s["seg1"] - 0.10)]
    for a_id, b_id in zip(order, order[1:]):
        t0, t1 = e[a_id] + 0.10, s[b_id] - 0.10
        if t1 - t0 >= 0.10:
            sil_windows.append((f"{a_id}->{b_id}", t0, t1))
    if 60.55 - (e["seg7"] + 0.10) >= 0.10:
        sil_windows.append(("tail_out", e["seg7"] + 0.10, 60.55))
    gap_sil = []
    sil_ok = True
    for label, t0, t1 in sil_windows:
        sl = slice(int(t0 * SR), int(t1 * SR))
        wv = wav_pcm[sl]
        dv = m4a_pcm[sl]
        w_max = float(np.abs(wv).max()) if wv.size else 0.0
        d_max = float(np.abs(dv).max()) if dv.size else 0.0
        d_db = 20 * math.log10(d_max + 1e-12)
        ok = (w_max == 0.0) and (d_db <= -100.0)
        sil_ok = sil_ok and ok
        gap_sil.append({"gap": label, "win": [round(t0, 2), round(t1, 2)],
                        "preencode_wav_abs_max": w_max,
                        "decoded_m4a_abs_max_db": round(d_db, 1),
                        "ok": bool(ok)})
        w_txt = "EXACT ZERO" if w_max == 0.0 else (
            f"{20 * math.log10(w_max + 1e-12):.1f}dB")
        print(f"[sil-check] gap {label} {t0:.2f}-{t1:.2f}: pre-encode "
              f"{w_txt} decoded={d_db:.1f}dB " + ("OK" if ok else "FAIL"))
    checks["gap_silence_check"] = gap_sil
    checks["gap_silence_ok"] = bool(sil_ok)
    checks["decoded_abs_max"] = round(float(np.abs(m4a_st).max()), 6)
    checks["decoded_true_peak_dbfs"] = round(
        20 * math.log10(float(np.abs(m4a_st).max()) + 1e-12), 2)
    checks["decoded_zero_clipping"] = bool(np.abs(m4a_st).max() < 1.0)
    print(f"[sil-check] decoded TRUE per-channel peak = "
          f"{checks['decoded_true_peak_dbfs']}dBFS "
          f"(abs max {checks['decoded_abs_max']}, zero clipping: "
          f"{checks['decoded_zero_clipping']})")

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
    ok_all = (all(g_["ok"] for g_ in gaps) and not overlaps
              and checks.get("gap_hf_ok", False)
              and checks.get("gap_silence_ok", False)
              and checks.get("decoded_zero_clipping", False)
              and bool(report["verify"].get("aac_peak_in_target", False))
              and bool(report["verify"].get("aac_zero_clipping", False)))
    print("AUDIO_BUILD_OK" if ok_all else "AUDIO_BUILD_WITH_WARNINGS")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
