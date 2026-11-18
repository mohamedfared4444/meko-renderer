#!/usr/bin/env python3
"""Generate the FINAL top-5 Gemini TTS voice comparison (Egyptian Arabic).

Candidate narrator voices for the official project narrator:
    top1_Enzo.mp3         Enzo          (needs fallback model chain)
    top2_Fenrir.mp3       Fenrir
    top3_Algenib.mp3      Algenib
    top4_Sadaltager.mp3   Sadaltager
    top5_Charon.mp3       Charon

Director's note: enhanced documentary-creator style (Zack D. Films /
Al-Da7ee7 vibe) + pure Cairene Masri text, NO classical tashkeel.

Enzo rule (user-specified):
  1) try voiceName "Enzo" on gemini-2.5-flash-preview-tts;
  2) on unsupported-voice error try, in order:
     gemini-3.1-flash-tts-preview -> gemini-3.8-flash-tts ->
     gemini-2.5-pro-preview-tts;
  3) if an API error message contains an official supported-voice list,
     record that list in the report and use the direct substitute so the
     remaining four voices still generate. top1_Enzo.mp3 then contains
     the substitute voice and the metadata marks it SUBSTITUTED.

Key sourcing (in-memory ONLY, never printed, never written to disk/logs):
  1) GEMINI_API_KEY env var, OR
  2) TURSO_DATABASE_URL + TURSO_AUTH_TOKEN env vars -> read-only SELECT
     from api_keys WHERE provider='gemini' (libsql HTTP v2/pipeline API).

Strict safety rules honored:
  - Read-only SELECT. No INSERT/UPDATE/DELETE anywhere.
  - Key lives only in the Python process memory; redacted from all logs.
  - No files in Meko Core / Manager are modified.

Exit codes: 0=all 5 generated, 4=partial (<5), 2=no TTS model,
            3=missing credentials.
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
                         "/home/z/my-project/download/voice-samples-top5")
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

MODEL_PRIMARY = "gemini-2.5-flash-preview-tts"
MODEL_PRO_FALLBACK = "gemini-2.5-pro-preview-tts"
MODEL_CHAIN_ENZO = [
    "gemini-2.5-flash-preview-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-3.8-flash-tts",
    "gemini-2.5-pro-preview-tts",
]
MODEL_CHAIN_STD = [MODEL_PRIMARY, MODEL_PRO_FALLBACK]

# 30 official prebuilt Gemini-TTS voice names (used to parse the official
# supported-voice list out of API error messages).
KNOWN_VOICE_NAMES = {
    "Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
    "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
    "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
    "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
    "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat",
}

# Direct substitutes for a failed Enzo (kept outside the top-5 comparison
# set so the listener gets maximum new information). First candidate that
# appears in the API's supported list wins; default last resort: Puck.
SUBSTITUTE_ORDER = ["Schedar", "Iapetus", "Achird", "Zubenelgenubi", "Puck"]

# Enhanced director's note (exact, user-specified) + pure Masri text
# without classical diacritics (would force Fusha intonation).
DIRECTIVE = (
    'Speak in a captivating, warm, and natural Egyptian Arabic '
    '(Cairene Masri) voice. Sound like a top-tier documentary creator '
    '(similar to Zack D. Films or Al-Da7ee7), curious, smooth, with '
    'natural human breathing, subtle enthusiasm, and zero robotic or '
    'formal Fusha tone: '
)
TEXT = (
    "النهارده هنشوف الشوكولاتة بتتعمل إزاي من الصفر! "
    "الحكاية بتبدأ من حبوب الكاكاو الخام، بتتحمص في أفران خاصة "
    "لحد ما ريحتها الغنية تطلع، وبعدين بتتطحن وتتحول لعجينة شوكولاتة ناعمة."
)
PROMPT = DIRECTIVE + '"' + TEXT + '"'

VOICES = [
    ("top1_Enzo.mp3", "Enzo"),
    ("top2_Fenrir.mp3", "Fenrir"),
    ("top3_Algenib.mp3", "Algenib"),
    ("top4_Sadaltager.mp3", "Sadaltager"),
    ("top5_Charon.mp3", "Charon"),
]

# globals filled while running, dumped into report.json at the end
SUPPORTED_VOICES_FROM_ERRORS: set = set()


def red(s: str) -> str:
    s = re.sub(r"AIza[0-9A-Za-z_\-]{3,}", "AIza[REDACTED]", s)
    s = re.sub(r"(?i)(authorization:\s*bearer\s+)\S+", r"\1[REDACTED]", s)
    return s


def parse_supported_voices(err_text: str) -> list:
    """Pull official voice names out of an API error message, if any."""
    found = set()
    for name in re.findall(r"[\"'\[(]([A-Z][A-Za-z]{3,})[\"'\],\]]", err_text):
        if name in KNOWN_VOICE_NAMES:
            found.add(name)
    return sorted(found)


def http_json(method: str, url: str, payload: dict | None, headers: dict,
              timeout: int = 90):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:600]
        return e.code, {"_error_body": red(body)}
    except urllib.error.URLError as e:
        return -1, {"_error_body": red(str(e)[:200])}


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


def tts_call(key: str, model: str, voice: str):
    """Returns (pcm_bytes, rate) | ("UNSUPPORTED_VOICE", msg) | None."""
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
        err = json.dumps(body) if "_error_body" in body else \
            json.dumps(red(json.dumps(body)))
        names = parse_supported_voices(err)
        if names:
            SUPPORTED_VOICES_FROM_ERRORS.update(names)
        low = err.lower()
        unsupported = ("voice" in low and
                       ("unsupported" in low or "invalid" in low or
                        "not supported" in low or "not found" in low))
        print(f"[tts:{voice}:{model}] HTTP {st}: {err[:260]}")
        if unsupported:
            return ("UNSUPPORTED_VOICE", err[:300])
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
         "format=duration:stream=sample_rate,channels", "-of", "json", path],
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


def resolve_voice(key: str, voice: str):
    """Try the model chain for one voice.

    Returns dict: {"status": "OK"|"FAILED", "model": ..., "voice": ...,
                   "attempts": [...]}
    Enzo gets the extended chain + direct-substitute rescue.
    """
    chain = MODEL_CHAIN_ENZO if voice == "Enzo" else MODEL_CHAIN_STD
    attempts = []
    unsupported_everywhere = False
    for model in chain:
        res = tts_call(key, model, voice)
        if isinstance(res, tuple) and res and res[0] == "UNSUPPORTED_VOICE":
            attempts.append({"model": model, "voice": voice,
                             "error": "unsupported_voice: " + res[1]})
            unsupported_everywhere = True
            continue
        if isinstance(res, tuple) and res and isinstance(res[0], bytes):
            attempts.append({"model": model, "voice": voice, "error": None})
            return {"status": "OK", "model": model, "voice": voice,
                    "attempts": attempts}, res
        attempts.append({"model": model, "voice": voice,
                         "error": "api/empty response"})
    # all models failed for this voice
    if voice == "Enzo" and unsupported_everywhere:
        supported = (SUPPORTED_VOICES_FROM_ERRORS
                     if SUPPORTED_VOICES_FROM_ERRORS else None)
        sub = None
        if supported:
            for cand in SUBSTITUTE_ORDER:
                if cand in supported:
                    sub = cand
                    break
        if not sub:
            sub = "Puck"  # known-good from the first evaluation round
        print(f"[enzo] unsupported on every model in the chain -> direct "
              f"substitute: {sub} "
              f"(official supported list seen: {sorted(supported) if supported
              else 'not present in error messages'})")
        for model in MODEL_CHAIN_STD:
            res = tts_call(key, model, sub)
            if isinstance(res, tuple) and res and isinstance(res[0], bytes):
                attempts.append({"model": model, "voice": sub, "error": None})
                return {"status": "SUBSTITUTED", "model": model,
                        "voice": sub, "substituted_for": "Enzo",
                        "attempts": attempts}, res
            attempts.append({"model": model, "voice": sub,
                             "error": "api/empty response"})
    return {"status": "FAILED", "model": None, "voice": voice,
            "attempts": attempts}, None


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
    print("[2] prompt directive: enhanced documentary-creator note, "
          f"{len(TEXT)} chars of Cairene Masri text, no tashkeel")

    report = {
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                          time.gmtime()),
        "purpose": "final top-5 narrator voice comparison (Egyptian Arabic)",
        "prompt": PROMPT,
        "models_visible_tts": tts_models,
        "enzo_model_chain": MODEL_CHAIN_ENZO,
        "voices": [],
        "supported_voices_from_api_errors": [],
    }

    ok = 0
    for fname, voice in VOICES:
        out = os.path.join(OUT_DIR, fname)
        meta, res = resolve_voice(key, voice)
        entry = {"file": fname, "requested_voice": voice}
        entry.update(meta)
        if not res:
            entry["status"] = "FAILED"
            entry["model"] = None
            print(f"[3] {fname} | {voice} | FAILED on every model")
            report["voices"].append(entry)
            continue
        pcm, rate = res
        if not pcm_to_mp3(pcm, rate, out):
            entry["status"] = "FAILED"
            entry["model"] = None
            entry["attempts"][-1]["error"] = "ffmpeg conversion failed"
            report["voices"].append(entry)
            continue
        dur, sr, mv = probe(out)
        size = os.path.getsize(out)
        good = dur > 5 and sr == 24000 and mv > -40
        status = ("OK" if meta["status"] == "OK" else "SUBSTITUTED")
        entry["actual_voice"] = meta["voice"]
        entry["model"] = meta["model"]
        entry["duration_s"] = round(dur, 2)
        entry["sample_rate"] = int(sr)
        entry["mean_volume_db"] = round(mv, 1)
        entry["size_bytes"] = size
        entry["probe_ok"] = bool(good)
        print(f"[3] {fname} | {voice} -> {meta['voice']} | "
              f"{meta['model']} | {dur:.1f}s | sr={sr:.0f}Hz "
              f"| mean {mv:.1f}dB | {size:,} B | "
              f"{status + ('/PROBE_OK' if good else '/PROBE_SUSPECT')}")
        report["voices"].append(entry)
        if good:
            ok += 1

    report["supported_voices_from_api_errors"] = \
        sorted(SUPPORTED_VOICES_FROM_ERRORS)
    rp = os.path.join(OUT_DIR, "report.json")
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    n_ok = sum(1 for v in report["voices"]
               if v.get("status") in ("OK", "SUBSTITUTED"))
    print(f"RESULT: {n_ok}/5 generated ({ok}/5 probe-clean) -> {OUT_DIR}")
    print("supported_voices_from_api_errors:",
          sorted(SUPPORTED_VOICES_FROM_ERRORS) or "(none observed)")
    return 0 if n_ok == 5 else 4


if __name__ == "__main__":
    sys.exit(main())
