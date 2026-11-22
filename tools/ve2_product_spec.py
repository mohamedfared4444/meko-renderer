#!/usr/bin/env python3
"""VE2 product-spec loader / validator (PHASE 5 STEP 1).

Single source of truth for product data. A product spec JSON fully
describes ONE product video:

  * product meta (id, Arabic/English titles, language)
  * voice (TTS provider/model/name/style directive)
  * video canvas (width/height/fps/frames/duration)
  * scenes (id, num, label, frozen cut window, optional Arabic chip)
  * narration segments (id, scene ref, exact TTS text, caption groups)
  * audio policy (lead, seg1->seg2 gap, anchors, post-cut offsets,
    per-segment internal-pause caps, pre/post-cut safety buffers)
  * banners (optional on-screen scene chips, consumed from Phase 5.2)
  * assets / outputs paths
  * optional `frozen` block = regression baseline of an approved build

The loader validates a spec against tools/schemas/ve2-product-spec.schema.json
(jsonschema when available, built-in fallback otherwise) plus semantic
template rules, then derives the EXACT structures the audio build consumes:

  CUTS, LEAD, G12, S5_ANCHOR, POST5, PAUSE_KEEP, caption groups, scene
  list and video meta  ->  ve2_build_audio_phase4.py
  SEGMENTS / MODEL / VOICE / DIRECTIVE  ->  gemini_tts_segments.py

so no product text or scene label lives in engine code any more.

CLI:
  python3 tools/ve2_product_spec.py validate  <spec.json>
  python3 tools/ve2_product_spec.py show      <spec.json>
  python3 tools/ve2_product_spec.py policy    <spec.json>
  python3 tools/ve2_product_spec.py skeleton  <spec.json> [--out FILE]
  python3 tools/ve2_product_spec.py check-chocolate [--spec S] [--timeline T]
"""

import argparse
import hashlib
import json
import os
import re
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
SCHEMA_PATH = os.path.join(TOOLS_DIR, "schemas", "ve2-product-spec.schema.json")
CHOCOLATE_SPEC = os.path.join(TOOLS_DIR, "products", "chocolate.json")
CHOCOLATE_TIMELINE = os.path.join(REPO_ROOT, "download", "ve2-audio-timeline.json")

# PHASE 5 template contract (what the placement optimizer + engine support
# in this step): 7 scenes / 7 narration segments; seg1+seg2 live in scene1,
# every later segN narrates scene(N-1). A future phase generalises this.
TEMPLATE_N = 7


class SpecError(Exception):
    """Raised when a product spec is invalid (schema or semantics)."""


# ---------------------------------------------------------------- JSON Schema

def _load_schema(path=SCHEMA_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _type_ok(x, t):
    if t == "object":
        return isinstance(x, dict)
    if t == "array":
        return isinstance(x, list)
    if t == "string":
        return isinstance(x, str)
    if t == "integer":
        return isinstance(x, int) and not isinstance(x, bool)
    if t == "number":
        return _is_number(x)
    if t == "boolean":
        return isinstance(x, bool)
    if t == "null":
        return x is None
    return True


def _fallback_validate(instance, schema, path="$", errors=None):
    """Minimal JSON-Schema subset validator (offline fallback). Supports the
    keywords used by ve2-product-spec.schema.json."""
    if errors is None:
        errors = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}, "
                      f"got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: value {instance!r} not in enum "
                      f"{schema['enum']!r}")
    t = schema.get("type")
    if t and not _type_ok(instance, t):
        errors.append(f"{path}: expected type {t}, got "
                      f"{type(instance).__name__}")
        return errors
    if "oneOf" in schema:
        ok = 0
        for sub in schema["oneOf"]:
            sub_errs = []
            _fallback_validate(instance, sub, path, sub_errs)
            if not sub_errs:
                ok += 1
        if ok != 1:
            errors.append(f"{path}: expected exactly 1 oneOf match, got {ok}")
    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property {req!r}")
        props = schema.get("properties", {})
        addl = schema.get("additionalProperties", True)
        for key, val in instance.items():
            if key in props:
                _fallback_validate(val, props[key], f"{path}/{key}")
            elif addl is False:
                errors.append(f"{path}: additional property {key!r} not allowed")
            elif isinstance(addl, dict):
                _fallback_validate(val, addl, f"{path}/{key}")
    if isinstance(instance, list):
        if "items" in schema:
            for i, item in enumerate(instance):
                _fallback_validate(item, schema["items"], f"{path}/{i}")
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{path}: more than {schema['maxItems']} items")
        if schema.get("uniqueItems"):
            canon = [json.dumps(x, sort_keys=True) for x in instance]
            if len(set(canon)) != len(canon):
                errors.append(f"{path}: items are not unique")
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']} chars")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: does not match pattern "
                          f"{schema['pattern']!r}")
    if _is_number(instance):
        for kw, op in (("minimum", lambda a, b: a >= b),
                       ("maximum", lambda a, b: a <= b),
                       ("exclusiveMinimum", lambda a, b: a > b),
                       ("exclusiveMaximum", lambda a, b: a < b)):
            if kw in schema and not op(instance, schema[kw]):
                errors.append(f"{path}: {kw} {schema[kw]} violated "
                              f"by {instance}")
    return errors


def _schema_errors(instance, schema):
    try:
        import jsonschema
    except ImportError:
        return _fallback_validate(instance, schema)
    errs = []
    v = jsonschema.Draft202012Validator(schema)
    for e in v.iter_errors(instance):
        errs.append(f"{e.json_path}: {e.message}")
    return errs


# ------------------------------------------------------------ semantic checks

def _semantic_errors(spec):
    errs = []
    lang = spec["product"]["language"]
    scenes = spec["scenes"]
    narr = spec["narration"]
    video = spec["video"]
    pol = spec["audio_policy"]

    # scenes: contiguous ids/nums, contiguous frozen windows
    ids = [s["id"] for s in scenes]
    want = [f"scene{i}" for i in range(1, len(scenes) + 1)]
    if ids != want:
        errs.append(f"scenes: ids must be contiguous scene1..scene{len(scenes)},"
                    f" got {ids}")
    for s in scenes:
        if s["num"] != f"{int(s['id'][5:]):02d}":
            errs.append(f"scenes/{s['id']}: num {s['num']!r} does not match id")
    if scenes[0]["start"] != 0.0:
        errs.append(f"scenes/scene1: start must be 0.0, got {scenes[0]['start']}")
    for a, b in zip(scenes, scenes[1:]):
        if a["end"] != b["start"]:
            errs.append(f"scenes/{b['id']}: start {b['start']} != previous "
                        f"end {a['end']}")
        if not a["end"] > a["start"]:
            errs.append(f"scenes/{a['id']}: window must be positive")
    if not scenes[-1]["end"] > scenes[-1]["start"]:
        errs.append("scenes/last: window must be positive")

    # video meta consistency
    if abs(scenes[-1]["end"] - video["duration_s"]) > 1e-6:
        errs.append(f"video/duration_s {video['duration_s']} != last scene "
                    f"end {scenes[-1]['end']}")
    if abs(video["frames"] - video["duration_s"] * video["fps"]) > 0.5:
        errs.append(f"video/frames {video['frames']} inconsistent with "
                    f"duration_s*fps {video['duration_s'] * video['fps']:.3f}")

    # narration: contiguous ids, template scene mapping, Arabic script check
    seg_ids = [n["id"] for n in narr]
    want_seg = [f"seg{i}" for i in range(1, len(narr) + 1)]
    if seg_ids != want_seg:
        errs.append(f"narration: ids must be contiguous seg1..seg{len(narr)},"
                    f" got {seg_ids}")
    scene_ids = set(ids)
    for n in narr:
        if n["scene"] not in scene_ids:
            errs.append(f"narration/{n['id']}: unknown scene ref {n['scene']!r}")
        m = re.match(r"^seg(\d+)$", n["id"])
        if m and int(m.group(1)) >= 3:
            expect = f"scene{int(m.group(1)) - 1}"
            if n["scene"] != expect:
                errs.append(f"narration/{n['id']}: template contract expects "
                            f"scene {expect}, got {n['scene']!r}")
        if n["id"] in ("seg1", "seg2") and n["scene"] != "scene1":
            errs.append(f"narration/{n['id']}: template contract expects "
                        f"scene1, got {n['scene']!r}")
        if lang.startswith("ar") and not re.search(r"[\u0600-\u06FF]", n["text"]):
            errs.append(f"narration/{n['id']}: language is {lang} but text "
                        f"has no Arabic characters")
    if lang.startswith("ar") and not re.search(r"[\u0600-\u06FF]",
                                               spec["product"]["title_ar"]):
        errs.append("product/title_ar: language is Arabic but title has no "
                    "Arabic characters")

    # template size (Phase 5 step 1: the optimizer + engine support 7/7)
    if len(scenes) != TEMPLATE_N or len(narr) != TEMPLATE_N:
        errs.append(f"template contract: expected {TEMPLATE_N} scenes and "
                    f"{TEMPLATE_N} narration segments "
                    f"(got {len(scenes)}/{len(narr)}); variable counts are "
                    f"planned for a later Phase 5 step")

    # audio_policy keys must reference real segments
    seg_set = set(seg_ids)
    for key, mapping in (("anchors_s", pol["anchors_s"]),
                         ("post_cut_offset_s", pol["post_cut_offset_s"]),
                         ("pause_keep_s", pol["pause_keep_s"])):
        for sid in mapping:
            if sid not in seg_set:
                errs.append(f"audio_policy/{key}: unknown segment {sid!r}")
    if "seg5" not in pol["anchors_s"]:
        errs.append("audio_policy/anchors_s: template contract requires a "
                    "'seg5' anchor (mid-scene4 placement)")
    if "seg7" not in pol["post_cut_offset_s"]:
        errs.append("audio_policy/post_cut_offset_s: template contract "
                    "requires a 'seg7' post-cut offset")
    anchor = pol["anchors_s"].get("seg5", 0.0)
    if not scenes[3]["start"] <= anchor <= scenes[3]["end"]:
        errs.append(f"audio_policy/anchors_s/seg5: anchor {anchor} outside "
                    f"scene4 window [{scenes[3]['start']}, {scenes[3]['end']}]")

    # banners (optional): window must coincide with a scene window
    for b in spec.get("banners", []):
        match = [s for s in scenes
                 if s["start"] == b["t0"] and s["end"] == b["t1"]]
        if not match:
            errs.append(f"banners/{b['num']}: window [{b['t0']}, {b['t1']}] "
                        f"does not match any scene window")
        elif match[0]["num"] != b["num"]:
            errs.append(f"banners/{b['num']}: num does not match scene num "
                        f"{match[0]['num']!r}")

    # frozen (optional): placements/ends_at keys must be real segments
    frozen = spec.get("frozen") or {}
    for key in ("placements_s", "ends_at_s"):
        for sid in frozen.get(key, {}):
            if sid not in seg_set:
                errs.append(f"frozen/{key}: unknown segment {sid!r}")
    return errs


# ---------------------------------------------------------------- public API

def load_spec(path):
    """Load + fully validate a product spec. Returns the spec dict or
    raises SpecError with every problem found."""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise SpecError(f"spec file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)
    except json.JSONDecodeError as e:
        raise SpecError(f"{path}: invalid JSON: {e}")
    errs = _schema_errors(spec, _load_schema())
    errs += _semantic_errors(spec)
    if errs:
        raise SpecError(f"{path}: {len(errs)} problem(s):\n  - " +
                        "\n  - ".join(errs))
    return spec


def audio_policy(spec):
    """Derive the EXACT structures the audio build consumes (same shapes and
    value semantics as the legacy hardcoded constants of
    ve2_build_audio_phase4.py)."""
    scenes = spec["scenes"]
    narr = spec["narration"]
    video = spec["video"]
    pol = spec["audio_policy"]
    seg_ids = [n["id"] for n in narr]
    return {
        # {"scene2": 14.35, ..., "scene7": 55.9} — scene N start == scene N-1 end
        "cuts": {s["id"]: s["start"] for s in scenes[1:]},
        "lead": pol["lead_s"],
        "g12": pol["gap_seg1_seg2_s"],
        "anchor_seg5": pol["anchors_s"]["seg5"],
        "post5": pol["post_cut_offset_s"]["seg7"],
        # {"seg1": None, ..., "seg5": 0.22, ...} — explicit overrides only
        "pause_keep": {sid: pol["pause_keep_s"].get(sid) for sid in seg_ids},
        "min_precut": pol["min_precut_buffer_s"],
        "min_postcut": pol["min_postcut_resume_s"],
        # exact float used for sample counts: 1819 / 30.0
        "video_dur_exact": video["frames"] / video["fps"],
        # rounded duration written verbatim into the timeline JSON
        "duration_json": video["duration_s"],
        "fps": video["fps"],
        "frames": video["frames"],
        "width": video["width"],
        "height": video["height"],
        # timeline JSON scene list: name/start/end in that key order
        "scenes_list": [{"name": s["label"], "start": s["start"], "end": s["end"]}
                        for s in scenes],
        # caption groups: {sid: [group, ...]} for segments that define them
        "groups_by_sid": {n["id"]: n["caption_groups"] for n in narr
                          if n.get("caption_groups")},
        "order": seg_ids,
    }


def video_meta(spec):
    """Timeline JSON video dict (key order matters for byte-identical JSON)."""
    v = spec["video"]
    return {"duration": v["duration_s"], "fps": v["fps"], "frames": v["frames"],
            "width": v["width"], "height": v["height"]}


def timeline_skeleton(spec):
    """Spec -> timeline STRUCTURE without audio-derived data. Demonstrates
    how scenes / narration segments / timeline map from the spec alone;
    placements and word timings are filled in by the audio build after TTS."""
    return {
        "video": video_meta(spec),
        "scenes": audio_policy(spec)["scenes_list"],
        "segments": [{"id": n["id"], "text": n["text"], "scene": n["scene"],
                      "placement": None, "ends_at": None, "words": [],
                      "note": "audio-derived fields pending TTS + audio build"}
                     for n in spec["narration"]],
    }


def spec_texts(spec):
    """[(seg_id, text)] — the exact TTS prompt lines, in template order."""
    return [(n["id"], n["text"]) for n in spec["narration"]]


# -------------------------------------------------------------------- helpers

def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------------ CLI

def _cmd_validate(args):
    spec = load_spec(args.spec)
    print(f"OK {args.spec}: schema + semantics valid")
    print(f"  product : {spec['product']['id']} ({spec['product']['title_ar']})")
    print(f"  scenes  : {len(spec['scenes'])}  segments: {len(spec['narration'])}"
          f"  duration: {spec['video']['duration_s']}s @ {spec['video']['fps']}fps")
    return 0


def _cmd_show(args):
    spec = load_spec(args.spec)
    pol = audio_policy(spec)
    p, v = spec["product"], spec["video"]
    print(f"product   : {p['id']} | {p['title_ar']} | {p['title_en']} | {p['language']}")
    print(f"voice     : {spec['voice']['provider']}/{spec['voice']['model']} "
          f"\"{spec['voice']['name']}\"")
    print(f"video     : {v['width']}x{v['height']} @ {v['fps']}fps = "
          f"{v['frames']} frames ({v['duration_s']}s)")
    print(f"policy    : lead={pol['lead']}s g12={pol['g12']}s "
          f"anchor(seg5)={pol['anchor_seg5']}s post5={pol['post5']}s "
          f"pause_keep={ {k: val for k, val in pol['pause_keep'].items() if val is not None} }")
    print("scenes:")
    for s in spec["scenes"]:
        chip = f"  chip={s['chip_ar']}" if s.get("chip_ar") else ""
        print(f"  {s['num']} {s['id']} {s['start']:7.2f}-{s['end']:7.2f}  {s['label']}{chip}")
    print("narration:")
    for n in spec["narration"]:
        grp = f"  groups={len(n['caption_groups'])}" if n.get("caption_groups") else ""
        text = n["text"] if len(n["text"]) <= 64 else n["text"][:61] + "..."
        print(f"  {n['id']} -> {n['scene']}: {text}{grp}")
    if spec.get("banners"):
        print("banners  :", ", ".join(
            f"{b['num']} {b['label_ar']} [{b['t0']}-{b['t1']}]" for b in spec["banners"]))
    if spec.get("frozen"):
        print("frozen    : regression baseline present "
              f"({len(spec['frozen'].get('output_md5', {}))} output md5s)")
    return 0


def _cmd_policy(args):
    spec = load_spec(args.spec)
    print(json.dumps(audio_policy(spec), ensure_ascii=False, indent=2))
    return 0


def _cmd_skeleton(args):
    spec = load_spec(args.spec)
    sk = timeline_skeleton(spec)
    js = json.dumps(sk, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(js + "\n")
        print(f"OK skeleton -> {args.out}")
    else:
        print(js)
    return 0


def _cmd_check_chocolate(args):
    spec_path = args.spec or CHOCOLATE_SPEC
    timeline_path = args.timeline or CHOCOLATE_TIMELINE
    fails = []
    spec = load_spec(spec_path)
    pol = audio_policy(spec)
    with open(timeline_path, "r", encoding="utf-8") as f:
        tl = json.load(f)

    def check(name, ok, detail=""):
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}"
              + (f" — {detail}" if detail and not ok else ""))
        if not ok:
            fails.append(name)

    print(f"check-chocolate: {spec_path} vs {timeline_path}")
    check("video meta", tl["video"] == video_meta(spec),
          f"timeline={tl['video']} spec={video_meta(spec)}")
    check("scenes (name/start/end)", tl["scenes"] == pol["scenes_list"])
    tl_seg = {s["id"]: s for s in tl["segments"]}
    check("segment ids", [s["id"] for s in tl["segments"]] == pol["order"])
    check("segment texts",
          all(tl_seg[n["id"]]["text"] == n["text"] for n in spec["narration"]))
    frozen = spec.get("frozen") or {}
    if frozen.get("placements_s"):
        check("frozen placements",
              all(abs(tl_seg[sid]["placement"] - val) < 1e-9
                  for sid, val in frozen["placements_s"].items()
                  if sid in tl_seg))
    if frozen.get("ends_at_s"):
        check("frozen ends_at",
              all(abs(tl_seg[sid]["ends_at"] - val) < 1e-9
                  for sid, val in frozen["ends_at_s"].items()
                  if sid in tl_seg))
    if pol["groups_by_sid"]:
        check("caption groups",
              all(tl_seg[sid].get("groups") == grp
                  for sid, grp in pol["groups_by_sid"].items() if sid in tl_seg))
    # frozen output md5 anchors (approved build integrity)
    repo_dl = os.path.join(REPO_ROOT, "download")
    md5_targets = {
        "audio_timeline": timeline_path,
        "narration_mix": os.path.join(repo_dl, "ve2-phase4-audio",
                                      "narration_mix_phase4.m4a"),
        "audio_verify": os.path.join(repo_dl, "ve2-phase4-audio-verify.json"),
        "timeline_js": os.path.join(REPO_ROOT, "prototype", "timeline.js"),
    }
    for key, fpath in md5_targets.items():
        want = frozen.get("output_md5", {}).get(key)
        if want and os.path.exists(fpath):
            check(f"frozen md5 {key}", _md5(fpath) == want,
                  f"actual={_md5(fpath)} expected={want}")
    if fails:
        print(f"check-chocolate: {len(fails)} FAILURE(S): {fails}")
        return 1
    print("check-chocolate: ALL PASS — spec reproduces the approved "
          "chocolate build exactly")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="VE2 product-spec loader/validator (Phase 5)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="validate a spec file")
    p.add_argument("spec")
    p.set_defaults(fn=_cmd_validate)

    p = sub.add_parser("show", help="human-readable spec summary")
    p.add_argument("spec")
    p.set_defaults(fn=_cmd_show)

    p = sub.add_parser("policy", help="print the derived audio-policy JSON")
    p.add_argument("spec")
    p.set_defaults(fn=_cmd_policy)

    p = sub.add_parser("skeleton", help="emit the timeline structure skeleton")
    p.add_argument("spec")
    p.add_argument("--out", default=None)
    p.set_defaults(fn=_cmd_skeleton)

    p = sub.add_parser("check-chocolate",
                       help="regression guard: spec vs committed timeline")
    p.add_argument("--spec", default=None)
    p.add_argument("--timeline", default=None)
    p.set_defaults(fn=_cmd_check_chocolate)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SpecError as e:
        print(f"SPEC ERROR:\n{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
