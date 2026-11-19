#!/usr/bin/env python3
"""Generate the 7 official narration segments with Enzo voice (FINAL narrator).

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


def trim_and_save(pcm: bytes, rate: int, out_flac: str):
    """s16le PCM -> silence-trimmed FLAC. Returns (raw_dur, trim_dur)."""
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
        p1 = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", tmp], capture_output=True, text=True)
        p2 = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out_flac], capture_output=True, text=True)
        try:
            raw = float(p1.stdout.strip())
            trimmed = float(p2.stdout.strip())
        except ValueError:
            return None, None
        return raw, trimmed
    finally:
        os.unlink(tmp)


def main() -> int:
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
    ok = 0
    for sid, text in SEGMENTS:
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
            report["segments"].append(entry)
            print(f"[{sid}] FAILED after {RETRIES} attempts")
            continue
        pcm, rate = res
        raw, trimmed = trim_and_save(pcm, rate, out)
        if trimmed is None:
            entry["status"] = "FAILED"
            report["segments"].append(entry)
            continue
        size = os.path.getsize(out)
        entry.update({"status": "OK", "rate": rate, "raw_dur": round(raw, 3),
                      "dur": round(trimmed, 3), "size": size})
        ok += 1
        print(f"[{sid}] OK raw={raw:.2f}s trimmed={trimmed:.2f}s {size:,}B")
        report["segments"].append(entry)

    with open(os.path.join(OUT_DIR, "segments_report.json"), "w",
              encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"RESULT: {ok}/7 segments OK -> {OUT_DIR}")
    return 0 if ok == 7 else 4


if __name__ == "__main__":
    sys.exit(main())
