#!/usr/bin/env python3
"""Generate the 7 official narration segments with Enzo voice (FINAL narrator).

PHASE 4.4 (clean container decode — root-cause companion fix):
  The TTS endpoint returns a COMPLETE RIFF/WAVE file (44-byte header +
  s16le PCM data chunk + ~7.7 KB C2PA content-credentials trailer).
  Writing those bytes to a .pcm file and decoding with -f s16le turned
  the header into a ~5 ms head blip and the trailer into a 160-305 ms
  -2 dBFS garbage block at the end of EVERY segment (the measured
  inter-sentence "هششش / TV-cut" source). trim_and_save now detects
  the container (RIFF/WAVE or MP3 sync) and lets ffmpeg demux it
  properly so ONLY real audio samples are written; the raw-s16le path
  is kept as a fallback for responses without container magic. An
  offline `--selftest` proves the fix on a synthetic WAV+trailer
  without any network call or API key.

Model: gemini-3.8-flash-tts (the only model that supports voiceName "Enzo"
— verified in the top-5 evaluation run 44390634477).
Voice: Enzo. Director's note: the winning documentary-creator directive.
Texts: 7 Cairene-Masri segments, no classical tashkeel, sized to scene windows.

Per segment:
  1) TTS call (retry x3) -> PCM s16le @ rate (from mimeType);
  2) ffmpeg silence trim: keep ~0.08s head, ~0.15s tail (threshold -45dB);
  3) save FLAC (lossless, small) + record raw/trimmed durations.

Output: $VE2_VOICE_OUT (default /home/z/my-project/download/ve2-narration-enzo)
  seg1_Enzo.flac ... seg7_Enzo.flac + segments_report.json

Key sourcing (in-memory ONLY): GEMINI_API_KEY env, or read-only Turso SELECT
fallback. AIza… patterns redacted from all output. Exit codes: 0=all 7 OK,
4=partial, 3=no key.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

OUT_DIR = os.environ.get("VE2_VOICE_OUT",
                         "/home/z/my-project/download/ve2-narration-enzo")
# Optional partial regeneration: VE2_ONLY_SEG="seg6" or "seg6,seg3".
# Existing OK entries in segments_report.json are preserved and merged.
ONLY = [s.strip() for s in os.environ.get("VE2_ONLY_SEG", "").split(",")
        if s.strip()]
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-3.8-flash-tts"
VOICE = "Enzo"
RETRIES = 3

# The winning director's note from the top-5 evaluation (verbatim).
DIRECTIVE = (
    'Speak in a captivating, warm, and natural Egyptian Arabic '
    '(Cairene Masri) voice. Sound like a top-tier documentary creator '
    '(similar to Zack D. Films or Al-Da7ee7), curious, smooth, with '
    'natural human breathing, subtle enthusiasm, and zero robotic or '
    'formal Fusha tone: '
)

# 7 segments — Egyptian Masri, sized to the frozen scene windows:
#   seg1 1.00-6.15 | seg2 6.50-14.55 | seg3 14.90-25.00 | seg4 25.35-36.80
#   seg5 37.15-44.35 | seg6 44.70-54.20 | seg7 54.55-60.30
SEGMENTS = [
    ("seg1", "النهارده هنشوف الشوكولاتة بتتعمل إزاي من الصفر."),
    ("seg2", "حبوب الكاكاو بتيجي من قرون شجرة الكاكاو، وبتوصلنا على سير النقل علطول."),
    ("seg3", "قبل التحميص الحبات بتتنضف كويس، وبعدين بتدخل طبلية التحميص الساخنة اللي بتطلع منها النكهة الغنية."),
    ("seg4", "وبعدين بتتطحن بين أسطانة حديد دوارة، بتتدوس الحبات لحد ما تبقى عجينة كاكاو سايحة."),
    ("seg5", "وبعدين تيجي المعالجة والخلط، تقليب على مهل بيحول العجينة لشوكولاتة سايحة ناعمة."),
    ("seg6", "الشوكولاتة السايحة بتتصب في القوالب، وبتعدى تونيل تبريد لحد ما تتماسك."),
    ("seg7", "وبكده الألواح بتطلع جاهزة، من حبة كاكاو لقطعة شوكولاتة."),
]


def red(s: str) -> str:
    s = re.sub(r"AIza[0-9A-Za-z_\-]{3,}", "AIza[REDACTED]", s)
    s = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", s)
    return s


def http_json(method, url, payload, headers, timeout=90):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {"_error_body": red(e.read().decode(errors="replace")[:400])}
    except urllib.error.URLError as e:
        return -1, {"_error_body": red(str(e)[:200])}


def key_from_env():
    v = os.environ.get("GEMINI_API_KEY", "").strip()
    return v or None


def turso_select_gemini_key():
    """Read-only SELECT fallback (never used on the Actions runner)."""
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    tok = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not url or not tok:
        return None
    if url.lower().startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    sql = ("SELECT api_key FROM api_keys WHERE provider='gemini' "
           "AND status != 'disabled' ORDER BY seq ASC LIMIT 1")
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    st, body = http_json("POST", url.rstrip("/") + "/v2/pipeline",
                         {"requests": [{"type": "execute",
                                        "stmt": {"sql": sql, "args": []}}]}, hdr)
    if st == 200:
        try:
            for r in body["results"][0]["response"]["result"]["rows"]:
                if r.get("type") == "row" and r.get("row"):
                    return str(r["row"][0])
        except (KeyError, IndexError, TypeError):
            pass
    return None


def tts_call(key, text):
    prompt = DIRECTIVE + '"' + text + '"'
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig":
                             {"prebuiltVoiceConfig": {"voiceName": VOICE}}},
        },
    }
    st, body = http_json("POST",
                         f"{API_BASE}/models/{MODEL}:generateContent",
                         payload, {"x-goog-api-key": key,
                                   "Content-Type": "application/json"},
                         timeout=180)
    if st != 200:
        err = json.dumps(body) if "_error_body" in body else \
            json.dumps(red(json.dumps(body)))
        print(f"[tts:{VOICE}:{MODEL}] HTTP {st}: {err[:260]}")
        return None
    try:
        for p in body["candidates"][0]["content"]["parts"]:
            inline = p.get("inlineData")
            if inline and inline.get("data"):
                mime = inline.get("mimeType", "")
                m = re.search(r"rate=(\d+)", mime)
                rate = int(m.group(1)) if m else 24000
                return base64.b64decode(inline["data"]), rate
    except (KeyError, IndexError, TypeError):
        pass
    print(f"[tts:{VOICE}:{MODEL}] no inlineData in response")
    return None


def decode_container(raw: bytes, rate: int) -> bytes:
    """PHASE 4.4: demux the TTS response properly before treating it as
    PCM. The endpoint returns a RIFF/WAVE container whose non-audio
    bytes (header + C2PA trailer) become audible garbage when decoded
    as raw s16le. Container responses are decoded via ffmpeg's demuxer
    (non-audio chunks are dropped); only responses without container
    magic fall back to the legacy raw-s16le interpretation. Offline:
    no network, no TTS call, no key."""
    if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
        suffix = ".wav"
        in_fmt = []
    elif raw[:3] == b"ID3" or raw[:2] in (b"\xff\xfb", b"\xff\xf3"):
        suffix = ".mp3"
        in_fmt = []
    else:
        suffix = ".pcm"          # legacy: genuinely raw s16le
        in_fmt = ["-f", "s16le", "-ar", str(rate), "-ac", "1"]
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(raw)
        tmp = f.name
    out = tmp + ".s16"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error"] + in_fmt +
            ["-i", tmp, "-map", "0:a:0",
             "-ac", "1", "-ar", str(rate), "-f", "s16le", out],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out):
            print("[decode]", r.stderr[:240])
            return raw           # fail-safe: never worse than before
        return open(out, "rb").read()
    finally:
        for p in (tmp, out):
            try:
                os.unlink(p)
            except OSError:
                pass


def trim_and_save(pcm: bytes, rate: int, out_flac: str):
    """s16le PCM -> silence-trimmed FLAC. Returns (raw_dur, trim_dur).
    PHASE 4.4: pcm is first demuxed through decode_container so
    container header/trailer bytes can never reach the FLAC."""
    pcm = decode_container(pcm, rate)
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as f:
        f.write(pcm)
        tmp = f.name
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.08,"
          "areverse,"
          "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.15,"
          "areverse")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(rate),
             "-ac", "1", "-i", tmp, "-af", af, "-c:a", "flac", out_flac],
            capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(out_flac):
            print("[ffmpeg]", r.stderr[:240])
            return None, None
        raw = len(pcm) / (rate * 2)      # decoded audio duration (exact)
        p2 = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out_flac], capture_output=True, text=True)
        try:
            trimmed = float(p2.stdout.strip())
        except ValueError:
            return None, None
        return raw, trimmed
    finally:
        os.unlink(tmp)


def load_existing_report():
    rp = os.path.join(OUT_DIR, "segments_report.json")
    if os.path.exists(rp):
        try:
            return json.load(open(rp, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return None


def selftest() -> int:
    """Offline proof of the PHASE 4.4 decode fix (no network, no key):
    synthesize a RIFF/WAVE file (44-byte header + 0.5 s 440 Hz s16le
    PCM + a fake 7716-byte C2PA-like trailer) and assert that
    decode_container() returns EXACTLY the data-chunk samples — the
    old raw-s16le path would have returned header+trailer as audio
    (measured in production as the -2 dBFS tail blob). Also asserts
    the legacy raw path is unchanged and trim_and_save end-to-end
    writes a FLAC of the right duration."""
    import math
    import struct
    rate = 24000
    n = rate // 2                       # 0.5 s of 440 Hz sine
    data = b"".join(
        struct.pack("<h", int(12000 * math.sin(
            2 * math.pi * 440 * k / rate))) for k in range(n))
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE" +
           b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate,
                                 rate * 2, 2, 16) +
           b"data" + struct.pack("<I", len(data)))
    wav = hdr + data + b"JUMBF" + b"A" * 7712   # fake C2PA trailer
    got = decode_container(wav, rate)
    ok = (len(got) == len(data) and got == data)
    print(f"[selftest] wav+trailer ({len(wav)}B) -> decoded "
          f"{len(got)}B (data chunk {len(data)}B): "
          + ("OK" if ok else "FAIL"))
    got_raw = decode_container(data, rate)
    ok2 = got_raw == data
    print(f"[selftest] raw s16le passthrough: "
          + ("OK" if ok2 else "FAIL"))
    tmp_flac = os.path.join(tempfile.gettempdir(), "ve2_selftest.flac")
    raw, trimmed = trim_and_save(wav, rate, tmp_flac)
    ok3 = (raw is not None and trimmed is not None
           and abs(trimmed - 0.5) <= 0.05 and raw < len(wav) / (rate * 2))
    print(f"[selftest] trim_and_save: raw={raw:.3f}s trimmed={trimmed:.3f}s "
          f"(expect ~0.500s, trailer excluded): "
          + ("OK" if ok3 else "FAIL"))
    try:
        os.unlink(tmp_flac)
    except OSError:
        pass
    if ok and ok2 and ok3:
        print("SELFTEST_OK")
        return 0
    print("SELFTEST_FAIL")
    return 5


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    key = key_from_env()
    if key:
        print("[key] source: GEMINI_API_KEY env var (in-memory)")
    else:
        key = turso_select_gemini_key()
        if key:
            print("[key] source: Turso read-only SELECT (in-memory)")
    if not key:
        print("RESULT: NO_KEY_AVAILABLE")
        return 3

    os.makedirs(OUT_DIR, exist_ok=True)
    report = {"model": MODEL, "voice": VOICE,
              "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                time.gmtime()),
              "directive": DIRECTIVE, "segments": []}
    # merge mode: keep previously OK segments when regenerating a subset
    prev = load_existing_report() if ONLY else None
    prev_by_id = {s["id"]: s for s in prev["segments"]} if prev else {}
    targets = [st for st in SEGMENTS if (not ONLY or st[0] in ONLY)]
    ok = 0
    for sid, text in targets:
        out = os.path.join(OUT_DIR, f"{sid}_Enzo.flac")
        entry = {"id": sid, "text": text}
        res = None
        for attempt in range(1, RETRIES + 1):
            res = tts_call(key, text)
            if res:
                break
            print(f"[{sid}] attempt {attempt}/{RETRIES} failed")
            time.sleep(2.0 * attempt)
        if not res:
            entry["status"] = "FAILED"
            if sid in prev_by_id and prev_by_id[sid].get("status") == "OK":
                entry = prev_by_id[sid]  # keep the previous good take
                print(f"[{sid}] regeneration failed -> keeping previous OK take")
            else:
                report["segments"].append(entry)
                print(f"[{sid}] FAILED after {RETRIES} attempts")
                continue
        else:
            pcm, rate = res
            raw, trimmed = trim_and_save(pcm, rate, out)
            if trimmed is None:
                entry["status"] = "FAILED"
                if sid in prev_by_id and prev_by_id[sid].get("status") == "OK":
                    entry = prev_by_id[sid]
                else:
                    report["segments"].append(entry)
                    continue
            else:
                size = os.path.getsize(out)
                entry.update({"status": "OK", "rate": rate,
                              "raw_dur": round(raw, 3),
                              "dur": round(trimmed, 3), "size": size})
                print(f"[{sid}] OK raw={raw:.2f}s trimmed={trimmed:.2f}s {size:,}B")
        report["segments"].append(entry)
        ok += 1

    if ONLY:
        merged = {k: prev_by_id[k] for k in prev_by_id if k not in ONLY}
        for e in report["segments"]:
            merged[e["id"]] = e
        report["segments"] = [merged[sid] for sid, _ in SEGMENTS if sid in merged]
        ok = sum(1 for e in report["segments"] if e.get("status") == "OK")

    with open(os.path.join(OUT_DIR, "segments_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"RESULT: {ok}/{len(SEGMENTS)} segments OK -> {OUT_DIR}")
    return 0 if ok == len(SEGMENTS) else 4


if __name__ == "__main__":
    sys.exit(main())
