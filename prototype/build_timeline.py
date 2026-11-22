#!/usr/bin/env python3
"""Generate scene/timeline.js from the approved audio timeline JSON.
Embeds scenes + narration segments (word-level timings) as a JS const.
Deterministic: pure transformation of the source JSON.

PHASE 5 STEP 1: source/output paths honor $VE2_DL / $VE2_ROOT (defaults
unchanged) so the pipeline can run against an isolated sandbox for
byte-identical regression verification."""
import json
import os

SRC = os.path.join(os.environ.get("VE2_DL", "/home/z/my-project/download"),
                   "ve2-audio-timeline.json")
OUT = os.path.join(
    os.environ.get("VE2_ROOT", "/home/z/my-project/visual-engine-2"),
    "scene/timeline.js")

d = json.load(open(SRC))

video = d["video"]
scenes = d["scenes"]
segments = []
for s in d["segments"]:
    seg = {
        "id": s["id"],
        "text": s["text"],
        "placement": round(s["placement"], 3),
        "endsAt": round(s["ends_at"], 3),
        "words": [{"w": w["w"], "t0": round(w["t0"], 3), "t1": round(w["t1"], 3)} for w in s["words"]],
    }
    # explicit caption-group rhythm override (e.g. seg7 end-card beats)
    if s.get("groups"):
        seg["groups"] = s["groups"]
    segments.append(seg)

payload = {"video": video, "scenes": scenes, "segments": segments}
js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

os.makedirs(os.path.dirname(OUT), exist_ok=True)

with open(OUT, "w", encoding="utf-8") as f:
    f.write("// AUTO-GENERATED from ve2-audio-timeline.json - do not edit by hand\n")
    f.write("window.VE2_TIMELINE = ")
    f.write(js)
    f.write(";\n")

total_words = sum(len(s["words"]) for s in segments)
print(f"OK timeline.js: {len(scenes)} scenes, {len(segments)} segments, {total_words} words, "
      f"duration={video['duration']}")
