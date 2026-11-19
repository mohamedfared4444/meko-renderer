#!/usr/bin/env python3
"""Chunked encode via python-spawned ffmpeg (survives sandbox watchdog).
30-frame chunks, auto-retry, then lossless concat + audio mux.
Run in background; progress written to output/encode.log (flushed)."""
import os, subprocess, sys

ROOT = "/home/z/my-project/visual-engine-2"
FRAMES = os.path.join(ROOT, "frames")
OUT = os.path.join(ROOT, "output")
TOTAL = 1819
CHUNK = 30
FPS = 30

def log(msg):
    print(msg, flush=True)

def run(cmd, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

def encode_chunk(start, n, cpath, attempt):
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-start_number", str(start), "-framerate", str(FPS),
           "-i", os.path.join(FRAMES, "f%05d.png"),
           "-frames:v", str(n),
           "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
           "-pix_fmt", "yuv420p", "-threads", "1",
           cpath]
    r = run(cmd)
    ok = r.returncode == 0 and os.path.exists(cpath) and os.path.getsize(cpath) > 0
    return ok, r

def main():
    chunk_files = []
    start, idx, failures = 0, 0, 0
    while start < TOTAL:
        n = min(CHUNK, TOTAL - start)
        cpath = os.path.join(OUT, f"chunk_{idx:03d}.mp4")
        # RESUME: skip chunks already written by a previous (interrupted) run
        if os.path.exists(cpath) and os.path.getsize(cpath) > 50000:
            chunk_files.append(cpath)
            start += n
            idx += 1
            continue
        done = False
        for attempt in range(1, 5):
            try:
                ok, r = encode_chunk(start, n, cpath, attempt)
            except subprocess.TimeoutExpired:
                ok = False; r = None
            if ok:
                done = True
                break
            log(f"retry idx={idx} start={start} attempt={attempt} rc={getattr(r,'returncode',None)}")
            failures += 1
            if os.path.exists(cpath): os.remove(cpath)
        if not done:
            log(f"FATAL chunk idx={idx} start={start}")
            sys.exit(2)
        chunk_files.append(cpath)
        start += n
        idx += 1
        if idx % 10 == 0:
            log(f"progress {start}/{TOTAL} (failures so far: {failures})")

    log(f"all {idx} chunks encoded (total retries: {failures})")

    lst = os.path.join(OUT, "concat.txt")
    with open(lst, "w") as f:
        for c in chunk_files:
            f.write(f"file '{c}'\n")
    vpath = os.path.join(OUT, "video_noaudio.mp4")
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", lst,
             "-c", "copy", vpath], timeout=120)
    if r.returncode != 0:
        log("CONCAT FAIL " + r.stderr[-400:]); sys.exit(4)
    log("concat done")

    final = os.path.join(OUT, "ve2-phase2-25d-enzo.mp4")
    r = run(["ffmpeg", "-y", "-v", "error", "-i", vpath,
             "-i", os.path.join(OUT, "narration_mix.m4a"),
             "-map", "0:v", "-map", "1:a",
             "-c", "copy", "-movflags", "+faststart", final], timeout=120)
    if r.returncode != 0:
        log("MUX FAIL " + r.stderr[-400:]); sys.exit(5)
    log("mux done")

    pr = run(["ffprobe", "-v", "error", "-select_streams", "v", "-count_packets",
              "-show_entries", "stream=nb_read_packets", "-of", "csv=p=0", final])
    vp = int(pr.stdout.strip() or "0")
    log(f"final video packets={vp} expected={TOTAL}")
    for c in chunk_files: os.remove(c)
    os.remove(lst)
    log("ENCODE_OK" if vp == TOTAL else "ENCODE_MISMATCH packets=%d" % vp)

if __name__ == "__main__":
    main()
