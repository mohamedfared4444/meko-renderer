#!/usr/bin/env python3
"""Generate 4 REAL Gemini TTS samples (Egyptian Arabic).

Key sourcing (in-memory ONLY, never printed, never written to disk/logs):
  1) GEMINI_API_KEY env var (direct path — fastest), OR
  2) TURSO_DATABASE_URL + TURSO_AUTH_TOKEN env vars -> read-only SELECT
     from api_keys WHERE provider='gemini' (libsql HTTP v2/pipeline API,
     same auth pattern as src/lib/turso.ts + merger/lib/db.js).

Strict safety rules honored:
  - Read-only SELECT. No INSERT/UPDATE/DELETE anywhere.
  - Key lives only in Python process memory; redacted from every log line.
  - No files in Meko Core / Manager are modified.

Exit codes: 0=done, 2=no TTS model, 3=missing credentials, 4=API errors.
"""
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

OUT_DIR = os.environ.get("VE2_VOICE_OUT", "/home/z/my-project/download/voice-samples-gemini")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL_PRIMARY = "gemini-2.5-flash-preview-tts"
MODEL_FALLBACK = "gemini-2.5-pro-preview-tts"

# Director's note in English (Gemini TTS convention) + the pure Masri text.
# No classical diacritics (would force Fusha intonation).
DIRECTIVE = (
    'Say in a warm, natural, energetic Egyptian Arabic (Masri) '
    'young Egyptian YouTuber voice, casual and spontaneous, '
    'no formal Fusha: '
)
TEXT = (
    "النهارده هنشوف الشوكولاتة بتتعمل إزاي من الصفر! "
    "الحكاية بتبدأ من حبوب الكاكاو الخام، بتتحمص في أفران خاصة "
    "لحد ما ريحتها الغنية تطلع، وبعدين بتتطحن وتتحول لعجينة شوكولاتة ناعمة."
)
PROMPT = DIRECTIVE + '"' + TEXT + '"'

VOICES = [
    ("gemini_sample1_Puck.mp3", "Puck"),
    ("gemini_sample2_Orus.mp3", "Orus"),
    ("gemini_sample3_Charon.mp3", "Charon"),
    ("gemini_sample4_Kore.mp3", "Kore"),
]


def red(s: str) -> str:
    s = re.sub(r"AIza[0-9A-Za-z_\-]{3,}", "AIza[REDACTED]", s)
    s = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", s)
    return s


def http_json(method: str, url: str, payload: dict | None, headers: dict,
              timeout: int = 90):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        return e.code, {"_error_body": red(body)}


# ---------------------------------------------------------------- key source
def key_from_gemini_env() -> str | None:
    v = os.environ.get("GEMINI_API_KEY", "").strip()
    return v or None


def turso_select_gemini_key() -> str | None:
    """Read-only SELECT from remote Turso api_keys (provider='gemini')."""
    url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    tok = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not url or not tok:
        return None
    if url.lower().startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    url = url.rstrip("/")
    sql = ("SELECT api_key FROM api_keys "
           "WHERE provider='gemini' AND status != 'disabled' "
           "ORDER BY seq ASC LIMIT 1")
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
    # v2 pipeline API
    st, body = http_json("POST", url + "/v2/pipeline",
                         {"requests": [{"type": "execute",
                                        "stmt": {"sql": sql, "args": []}}]},
                         hdr)
    if st == 200:
        try:
            rows = (body["results"][0]["response"]["result"]["rows"])
            for r in rows:
                if r.get("type") == "row" and r.get("row"):
                    return str(r["row"][0])
        except (KeyError, IndexError, TypeError):
            pass
    # v1 fallback
    st, body = http_json("POST", url + "/v1/execute", {"sql": sql}, hdr)
    if st == 200:
        try:
            for r in body["results"]:
                v = r.get("row") or []
                if v:
                    return str(v[0])
        except (KeyError, TypeError):
            pass
    print("[db] SELECT failed or no gemini key row (status=%d)" % st)
    return None


def get_key() -> str | None:
    k = key_from_gemini_env()
    if k:
        print("[key] source: GEMINI_API_KEY env var (in-memory)")
        return k
    k = turso_select_gemini_key()
    if k:
        print("[key] source: Turso api_keys read-only SELECT (in-memory)")
        return k
    return None


# ------------------------------------------------------------------- gemini
def list_tts_models(key: str) -> list[str]:
    st, body = http_json("GET", API_BASE + "/models", None,
                         {"x-goog-api-key": key})
    names = []
    if st == 200:
        for m in body.get("models", []):
            n = m.get("name", "")
            if "tts" in n.lower():
                names.append(n.replace("models/", ""))
    else:
        print("[models.list] failed:", st, json.dumps(body)[:200])
    return names


def tts_call(key: str, model: str, voice: str) -> bytes | None:
    payload = {
        "contents": [{"parts": [{"text": PROMPT}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig":
                             {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    st, body = http_json("POST", f"{API_BASE}/models/{model}:generateContent",
                         payload, {"x-goog-api-key": key,
                                   "Content-Type": "application/json"},
                         timeout=180)
    if st != 200:
        print(f"[tts:{voice}:{model}] HTTP {st}: "
              f"{json.dumps(red(json.dumps(body)))[:260]}")
        return None
    try:
        parts = body["candidates"][0]["content"]["parts"]
        for p in parts:
            inline = p.get("inlineData")
            if inline and inline.get("data"):
                mime = inline.get("mimeType", "")
                m = re.search(r"rate=(\d+)", mime)
                rate = int(m.group(1)) if m else 24000
                print(f"[tts:{voice}:{model}] PCM ok, mime={mime.split(';')[0]}"
                      f" rate={rate}")
                return base64.b64decode(inline["data"]), rate
    except (KeyError, IndexError, TypeError):
        pass
    print(f"[tts:{voice}:{model}] no inlineData in response")
    return None


def pcm_to_mp3(pcm: bytes, rate: int, out_path: str) -> bool:
    with tempfile.NamedTemporaryFile(suffix=".pcm", delete=False) as f:
        f.write(pcm)
        tmp = f.name
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-f", "s16le", "-ar", str(rate),
             "-ac", "1", "-i", tmp, "-c:a", "libmp3lame", "-q:a", "3",
             out_path],
            capture_output=True, text=True)
        if r.returncode != 0:
            print("[ffmpeg]", r.stderr[:200])
            return False
        return os.path.getsize(out_path) > 10000
    finally:
        os.unlink(tmp)


def probe(path: str) -> tuple[float, float, float]:
    d = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:stream=sample_rate", "-of", "json", path],
        capture_output=True, text=True)
    try:
        j = json.loads(d.stdout)
        dur = float(j["format"]["duration"])
        sr = float(j["streams"][0]["sample_rate"])
    except Exception:  # noqa: BLE001
        return -1, -1, -1
    v = subprocess.run(
        ["ffmpeg", "-v", "info", "-i", path, "-af", "volumedetect",
         "-f", "null", "-"], capture_output=True, text=True)
    mv = re.search(r"mean_volume: ([-\d.]+)", v.stderr)
    return dur, sr, float(mv.group(1)) if mv else -99


def main() -> int:
    key = get_key()
    if not key:
        print("RESULT: NO_KEY_AVAILABLE")
        print("  need GEMINI_API_KEY  OR  TURSO_DATABASE_URL + TURSO_AUTH_TOKEN")
        return 3

    print("[1] key acquired in-memory (never printed)")
    tts_models = list_tts_models(key)
    print("[1] TTS-capable models visible to this key:",
          tts_models or "(none listed)")

    os.makedirs(OUT_DIR, exist_ok=True)
    model = MODEL_PRIMARY
    if tts_models and MODEL_PRIMARY not in tts_models:
        if MODEL_FALLBACK in tts_models:
            model = MODEL_FALLBACK
        else:
            print(f"[2] neither {MODEL_PRIMARY} nor {MODEL_FALLBACK} "
                  f"available for this key")
            return 2
    print(f"[2] using model: {model}")

    ok = 0
    for fname, voice in VOICES:
        out = os.path.join(OUT_DIR, fname)
        res = tts_call(key, model, voice)
        if not res:
            continue
        pcm, rate = res
        if not pcm_to_mp3(pcm, rate, out):
            print(f"[3] {fname}: conversion failed")
            continue
        dur, sr, mv = probe(out)
        size = os.path.getsize(out)
        status = "OK" if (dur > 5 and sr == 24000 and mv > -40) else "SUSPECT"
        print(f"[3] {fname} | {voice} | {dur:.1f}s | sr={sr:.0f}Hz "
              f"| mean {mv:.1f}dB | {size:,} B | {status}")
        if status == "OK":
            ok += 1
    print(f"RESULT: {ok}/4 samples OK -> {OUT_DIR}")
    return 0 if ok == 4 else 4


if __name__ == "__main__":
    sys.exit(main())
