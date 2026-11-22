# Meko Visual Engine 2.0 — Phase 4 Delivery Report
**Branch:** `visual-engine-2-prototype` (mohamedfared4444/meko-renderer) · **Date:** 2026-11-19
**Commits:** `07c7c37` (Part A+B audio) → `edee146` (final render + proofs)
**Deliverable:** `download/ve2-phase4-25d-enzo-sfx.mp4` — 1080×1920 @30 fps, 1819 frames, 60.633 s, AAC 192k 48 kHz stereo

Raw link: `https://raw.githubusercontent.com/mohamedfared4444/meko-renderer/visual-engine-2-prototype/download/ve2-phase4-25d-enzo-sfx.mp4` (verified HTTP 206)

---

## 1. PART A — Segment pacing (before → after)

Enzo's raw clips were kept **natural** (no pause surgery) except seg5/seg7, whose scene windows are tight. No TTS re-call; word timings recomputed from the real final audio envelope (RMS bursts → char-share → silence snapping). All starts respect scene semantics; every scene cut keeps ≥0.35 s pre-cut quiet buffer.

| Seg | Before (s) start→end | After (s) start→end | Gap before → after |
|---|---|---|---|
| lead-in | 1.000 | 1.600 | — |
| seg1 | 1.000 → 4.921 | 1.600 → 5.266 | — |
| seg2 | 6.500 → 12.501 | 5.986 → 12.132 | **1.579 → 0.720** |
| seg3 | 14.900 → 22.821 | 14.939 → 23.585 | **2.399 → 2.807** |
| seg4 | 25.350 → 33.511 | 26.392 → 34.343 | **2.529 → 2.807** |
| seg5 | 37.150 → 43.764 | 37.150 → 43.701 | **3.639 → 2.807** |
| seg6 | 44.700 → 51.421 | 45.948 → 52.414 | **0.936 → 2.247** |
| seg7 | 54.550 → 60.185 | 54.660 → 60.046 | **3.129 → 2.246** |
| tail | 0.448 | 0.587 | — |

**Honest note on the 0.35–0.75 s target:** the 7 Enzo clips total ~45.7 s of speech on a frozen 60.633 s video, so ~15 s of silence must exist somewhere. With narration semantically locked to its scene (non-straddling, ≥0.35 s buffers at the 5 scene cuts), the mathematically best-uniform distribution puts the within-scene gap at **0.72 s** (hit the target) and equalizes the cross-cut gaps into a **consistent 2.25–2.81 s scene-breath** (they were erratic 0.94–3.64 s before; worst gap −23 %). Part B's SFX now fills those breaths, so they read as intentional sound-design beats, not dead air. Any tighter would require J-cut straddling of scene cuts (rejected: breaks the ≥0.35 s scene-transition buffer rule) or re-writing/shortening the narration audio.

- Zero speech overlaps (verified from the RMS speech mask, `speech_overlaps: []`).
- Boundary gaps at all 5 cuts ≥ 0.46 s (cut4 min), video end 0.587 s.
- Single-Pop captions: 80 words, chunk sweep worst = **2 words / 1 chunk** across 0.2–60.5 s; seg7 end cadence preserved via explicit groups: «وبكده الألواح» → «بتطلع جاهزة» → «من حبة» → «كاكاو» → «لقطعة» → «شوكولاتة».
- Sources regenerated from the single JSON: `ve2-audio-timeline.json` → `timeline.js` (both in `prototype/` and snapshot `prototype-sources/phase1-v2/`).

## 2. PART B — Deterministic factory SFX (seed 987126)

All synthesized in numpy; the only stochastic element is one `np.random.RandomState(987126)` noise source (byte-identical across runs — no `Math.random()`, no external/copyrighted assets). Each family is gated to its scene window with 0.45 s raised-cosine fades (no clicks), bus normalized to **−32 dB mean** (under the −16.5 dB voice, above the −35 dB pad).

| Stage | Window | SFX content |
|---|---|---|
| Conveyor | 0.05–14.35, 44.17–54.40 | 55/110 Hz hum + 40–120 Hz roller rumble + 0.36 s belt-speed roller ticks + slow belt surge AM |
| Roasting | 14.40–24.70 | 120–350 Hz burner whoosh (0.35 Hz breathing) + 70 Hz drum tumbler thumps (1.25 s rotation) + seeded bean crackle (~3.2/s, 1.5–3.2 kHz) |
| Grinding | 24.90–36.75 | 65 Hz harmonic gear stack (×6) + 250–700 Hz mechanical band + 4.6 Hz roller-rhythm AM |
| Conching | 36.95–44.05 | 300–900 Hz liquid swirl (0.18 Hz wobble) + 180 Hz vibrato liquid tone with gentle beating |
| Pouring | 44.40–52.60 | 1.2–3.5 kHz stream with 0.8 Hz deposit rhythm + 26 seeded drip accents |
| Cooling | 48.50–54.40 | 2.5–6 kHz cold air + chime accents (1568/2093 Hz at 48.9/51.2/53.4) + demold exit whoosh at 54.45–54.75 |

## 3. Audio measurements

| Metric | Target | Measured |
|---|---|---|
| Narration speech mean (limited) | −16.5…−18 dB | **−16.79 dB** |
| Music pad mean | −35 dB | **−35 dB** (gain −19.32 dB applied) |
| SFX bus mean | gentle, under voice | **−32 dB** (gain −23.68 dB applied) |
| Mix WAV peak | < −1.3 dBFS | −1.54 dBFS (no guard scaling needed) |
| AAC decoded peak | ~−1.3…−1.5 dBFS, zero clipping | **−1.36 dBFS** (scale 0.0 dB) |
| Ambient windows (pad+SFX) | quiet, non-fatiguing | −33.9…−38.5 dB mean |
| Speech windows in mix | −16.5…−18 dB | −16.8…−18.0 dB |
| Duration | 60.633 s | 60.633 s |

The AAC ladder accepted the first encode (−1.36 dBFS); decoded max via volumedetect on the final MP4: **−1.4 dB — zero clipping**.

## 4. Automated test results — 12/12 PASS

| Test | Result |
|---|---|
| title (t=1.0 no machine overlap) | PASS |
| gap40 (tank→funnel corridor clean) | PASS |
| endCard (safe margins t=59) | PASS |
| caption24 (≤1 chunk, ≤2 words) | PASS |
| captionSweep (≤2 words, 0.2–60.5 s) | PASS (worst 2) |
| tunnelExit (bar level through exit) | PASS |
| heroEntrance (smooth fade 55.8–56.5) | PASS |
| banners (funnel + tunnel visible) | PASS |
| chips (label/bean gap ≥5 px) | PASS |
| moldOverlap (≤1 mold in spout zone) | PASS |
| inletClean (mixing inlet 37.5/42.0) | PASS |
| determinism (byte-identical re-render t=25/40/59) | PASS |

**Zero-visual-regression proof:** frame-exact MP4-vs-MP4 comparison at caption-free timestamps t=13.6/35.5/53.2 (frames 408/1065/1596) → **MAD 0.0000, 100.00 % identical pixels** (`ve2-phase4-regression-check.json`). Phase-2's 2.5D visuals are bit-for-bit preserved; only captions and audio changed.

## 5. Safety confirmation

- Work exclusively on `visual-engine-2-prototype`; `main`, Meko Core (`mohamedfared4444/Meko`), Meko Manager, Turso, Vercel settings — **untouched** (remote `origin/main` last commit unchanged; single-branch clone).
- No secrets printed/committed; audio pipeline runs fully offline in the sandbox (no TTS call, no API key involved this phase).
- Backups before modification: `output/audio/phase2_backup/` (Phase-2 timeline JSON, verify JSON, timeline.js). Phase-2 MP4 remains untouched at `download/ve2-phase2-25d-enzo.mp4`.
- Pushed artifacts: final MP4 (55.1 MB), contact sheet, verify JSONs, audio tools (`tools/ve2_build_audio_phase4.py`), updated `prototype/` + `prototype-sources/phase1-v2/` + local `download/ve2-engine-source/` snapshots.

## 6. Files

- `download/ve2-phase4-25d-enzo-sfx.mp4` — final video
- `download/ve2-phase4-contact-sheet.jpg` — 12-tile scene contact sheet
- `download/ve2-audio-timeline.json` — single source of truth (placements + word timings)
- `download/ve2-phase4-audio-verify.json` — full audio measurement log
- `download/ve2-phase4-regression-check.json` — pixel-identity proof
- `download/ve2-phase4-audio/narration_mix_phase4.m4a` + deterministic SFX bus WAV (seed 987126)
- `tools/ve2_build_audio_phase4.py` — reproducible Part A+B builder

---

# Phase 4.1 Update — Harsh SFX removal («نغمشة» fix)

**Date:** 2026-11-19 · **Trigger:** user reported an unpleasant crackly/hissy/ticking noise («نغمشة») after speech / between narration lines, caused by the Phase-4 procedural SFX bus.

## What changed

- `tools/ve2_build_audio_phase4.py`: **all procedural SFX layers disabled** (`SFX_ENABLED = False`; `build_sfx()` now returns digital silence — the harsh generators — roller ticks ~1.9 kHz, seeded bean crackle 1.5–3.2 kHz, drip accents 2.4 kHz, all band-noise hiss/swirl families (40–120, 120–350, 250–700, 300–900, 1.2–3.5, 2.5–6 kHz), chime pings 1568/2093 Hz, exit whoosh — are removed from the builder). The mix is now **narration + warm deterministic ambient music pad only**.
- **Segment placements / word timings / timeline.js / 2.5D frames: untouched.** `ve2-audio-timeline.json` is byte-identical to the Phase-4 version (md5 `46df7fe8…` before = after); regenerated `prototype/timeline.js` is byte-identical (md5 `275e319a…`); video stream MD5 of the re-muxed MP4 is identical to Phase 4 (`b7f3cd30…`) — frames bit-for-bit unchanged.

## Audio measurements (Phase 4 → Phase 4.1)

| Metric | Phase 4 (SFX on) | Phase 4.1 (SFX off) | Target |
|---|---|---|---|
| Narration speech mean (limited) | −16.79 dB | **−16.79 dB** (unchanged) | −16.5…−18 dB |
| Music pad mean | −35 dB | **−35 dB** (gain −19.32 dB) | −35 dB |
| SFX bus | −32 dB (removed) | **digital silence** | — |
| AAC decoded peak | −1.36 dBFS | **−1.47 dBFS** (ladder −0.55 dB) | ~−1.3…−1.5 dBFS, zero clipping |
| Mix WAV peak | −1.54 dBFS | **−1.54 dBFS** | < −1.3 dBFS |
| Mix duration | 60.633 s | **60.633 s** | 60.633 s |
| Speech windows (decoded MP4) | −16.8…−18.0 dB | **−17.4…−18.6 dB** mean, max −2.2…−2.3 dB | −16.5…−18 dB |
| Ambient windows (pad only) | −33.9…−38.5 dB (max −25.7…−26.7) | **−34.5…−39.1 dB mean (max −26.7…−27.3)** | quiet, non-fatiguing |

## Zero-crackle/hiss/tick proof (new automated check)

Hann-weighted rFFT band analysis of every narration-gap window, SFX zone = 1.5–19 kHz (all removed layers lived there; the warm pad tops out at ~785 Hz):

| Gap window | Phase 4 (with SFX) | Phase 4.1 decoded m4a | Phase 4.1 pre-encode WAV |
|---|---|---|---|
| 5.37–5.89 s (roller ticks were here) | −115.1 dB | **−135.0 dB** | −212.0 dB |
| 34.54–36.70 s | −137.0 dB | **−138.6 dB** | −220.1 dB |
| 52.61–54.46 s (cold-air hiss + chime were here) | **−64.8 dB** | **−133.7 dB** | −218.3 dB |
| 0.05–1.50 s (roller ticks were here) | −109.5 dB | **−140.1 dB** | −192.5 dB |

The pre-encode mix WAV contains **mathematically zero** energy above 1.5 kHz in all gaps (−192…−220 dB = float rounding); the decoded AAC floor (−134…−140 dB) is codec noise ~70 dB below the old SFX residue. Check criterion ≤ −100 dB: **4/4 PASS** (`gap_hf_ok: true` in `ve2-phase4-audio-verify.json`). Gap boundary checks 6/6 OK, speech overlaps: none.

## Verification re-run

- **determinism:** two independent rebuilds → `narration_mix_phase4.m4a` byte-identical (md5 `eddc8939…`); decoded audio PCM in the MP4 identical to the m4a (md5 `c636b3fe…`); video stream MD5 unchanged.
- **captionSweep:** frame-exact extraction old-vs-new MP4 at 6 timestamps (caption-active t=3.0/8.0/57.5 «شوكولاتة» + caption-free t=5.5/35.5/60.4) → **MAD 0.0000, 100 % identical pixels** on all frames (`ve2-phase41-caption-sweep.json`).
- **audio peak/duration:** MP4 audio astats peak **−1.474 dBFS**, RMS −19.4 dB, duration **60.633333 s**, 1819 frames, 1080×1920 @30 fps — all PASS.

## Phase 4.1 files

- `download/ve2-phase4-25d-enzo-sfx.mp4` — re-muxed deliverable (video stream copied bit-exact, clean audio)
- `download/ve2-phase4-audio/narration_mix_phase4.m4a` — clean narration + pad mix (replaced; the Phase-4 with-SFX mix remains in git history at `edee146`, and `sfx_bus_deterministic_seed987126.wav` is kept as reference of what was removed)
- `download/ve2-phase4-audio-verify.json` — updated with `sfx_enabled: false`, gap HF check, new measurements
- `download/ve2-phase41-caption-sweep.json` — caption/frame identity proof

---

# Phase 4.2 — Music pad removal ("هششش / TV-switch" fix)

**Commit:** this section · **Date:** 2026-11-22 · **Parent:** `a11b509` (Phase 4.1)

## User report

After the Phase 4.1 SFX removal the user STILL heard a soft "هششش" between narration lines — a sound like a TV channel-switching or a TV turning off. With the SFX bus already digital silence, the only remaining non-speech source in the mix was the **warm ambient music pad**: its chord-boundary envelope ramps (1.0 s release every ~15.16 s), 0.25 Hz tremolo and 2.5 s end fade can read as a faint "TV cut" under quiet gaps. Conclusion: for this prototype the pad must go entirely.

## Change set (`tools/ve2_build_audio_phase4.py`)

1. `MUSIC_ENABLED = False` alongside `SFX_ENABLED = False` — the music bus gain is **exactly 0.0** in the mix (muted buses contribute IEEE-exact zero, so gap samples stay digital zero; the pad generator itself is kept for reference/history).
2. **20 ms raised-cosine micro-fades** at every segment edge, applied on the MIX BUS ONLY (`finals[...]` untouched), so no hard level step remains at any speech onset/offset and placements/word timings cannot move.
3. New verifications:
   - `gap_silence_check` — every narration gap (lead-in, all 6 inter-segment gaps, tail-out) must be **MATHEMATICALLY ZERO** in the pre-encode WAV (windows start 0.10 s past the ±0.08 s trim pads) and ≤ −100 dB in the decoded m4a.
   - AAC peak check tightened: decoded true per-channel peak must land in **[−1.90, −1.30] dBFS** (target ≈ −1.45), zero clipping by construction; ladder results logged per pass.
   - Peak measurement fixed to TRUE per-channel decode: the first 4.2 run showed a bogus 1.106 abs-max because a mono downmix applies libswresample's 0.7071 coefficient per channel (up to +3.01 dB on correlated L/R); the file's real peak was −2.13 dBFS.
4. Unchanged by design (md5-proven below): segment placements, word timings, `ve2-audio-timeline.json`, `timeline.js`, 2.5D frames.

## Measurements (pure Enzo narration mix)

| Metric | Phase 4.1 | **Phase 4.2** | Spec |
|---|---|---|---|
| Narration limited speech mean | −16.79 dB | **−16.80 dB** | −16.5…−18 dB ✔ |
| Pre-encode mix peak | −1.54 dBFS | **−2.00 dBFS** | (limiter ceiling) ✔ |
| AAC decoded peak (true per-ch) | −1.47 dBFS | **−1.48 dBFS** (abs max 0.8432) | −1.3…−1.5 dBFS, zero clipping ✔ |
| AAC ladder choice | −0.55 dB | **−0.18 dB** (pass 3 of 6) | closest to −1.45 ✔ |
| Ambient-gap level (volumedetect) | −34.6…−39.1 dB (music pad) | **−91.0 dB (s16 floor)** | no music ✔ |
| Gap 1.5–19 kHz band (decoded) | −134…−140 dB | **exact zero (−240 dB reading)** | ≤ −100 dB ✔ |
| Gap pre-encode WAV | −192…−220 dB | **EXACT ZERO (0.0)** | digital silence ✔ |
| Mix duration / mean / max | 60.633 s / −19.3 dB / −1.9 dB | **60.633 s / −19.2 dB / −1.5 dB** | ✔ |

**`AUDIO_BUILD_OK`** — boundary gaps 6/6 OK, `speech_overlaps: []`, `gap_hf_ok: true`, `gap_silence_ok: true`, `aac_peak_in_target: true`, `decoded_zero_clipping: true`. Full AAC ladder (deterministic): +0.00 → −0.56, −0.12 → −1.14, −0.18 → −1.48 ✔, −0.24 → −1.73, −0.30 → −2.13, −0.55 → −2.30 dBFS.

## Identity proofs (nothing visual touched)

- `ve2-audio-timeline.json` md5 **`46df7fe8…`** — byte-identical to Phase 4.1/4.0.
- `prototype/timeline.js` md5 **`275e319a…`** — byte-identical.
- Re-mux: video stream copied (`-c:v copy`) → video stream MD5 **`b7f3cd30…`** unchanged; **1819 frames**, 1080×1920 @30 fps, **60.633333 s**.
- MP4 audio astats: overall peak **−1.481 dBFS** (ch1 −1.481 / ch2 −2.000 — joint-stereo mid/side quantization; overall max is the binding figure), zero clipping.
- **determinism:** two independent builds → `narration_mix_phase4.m4a` byte-identical (md5 `878dddf7…`), verify JSON byte-identical (md5 `7d932bef…`).
- **captionSweep** (`ve2-phase42-caption-sweep.json`): both MP4s decode 1819/1819 frames; all 6 sweep frames (caption-active 3.0/8.0/57.5, caption-free 5.5/35.5/60.4) **MD5-identical old-vs-new** → combined with the stream-level MD5 equality, captions and all burned-in visuals are provably unchanged.

## Phase 4.2 files

- `download/ve2-phase4-25d-enzo-sfx.mp4` — re-muxed deliverable (pure narration audio, video bit-exact)
- `download/ve2-phase4-audio/narration_mix_phase4.m4a` — pure Enzo narration mix (md5 `878dddf7…`)
- `download/ve2-phase4-audio-verify.json` — updated with `music_enabled: false`, `gap_silence_check`, AAC ladder, true per-channel peak
- `download/ve2-phase42-caption-sweep.json` — frame identity proof
- `tools/ve2_build_audio_phase4.py` — Phase 4.2 change set (docstring documents rationale)

## Honest notes

- The mix is now **pure narration**: no music, no SFX. If a future pass wants ambience back, the pad must be redesigned with gap-safe envelopes (e.g., level-locked under −50 dB in narration gaps, no chord-boundary ramps) — flip `MUSIC_ENABLED` only then.
- AAC overshoot is strongly non-monotonic for this content (−0.12 dB → −1.14 dBFS but −0.30 dB → −2.13 dBFS), which is why the ladder uses 0.06 dB steps around the target.
- Two build runs hit the sandbox's 590/600 s shell timeout at the very END of the run (log complete, `AUDIO_BUILD_OK` printed, artifacts flushed); a re-mux verification command also returned exit −9 (SIGKILL) after printing all results. No data was affected.
