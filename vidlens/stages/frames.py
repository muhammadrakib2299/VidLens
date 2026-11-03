"""FRAMES stage — extract candidate key frames.

CCTV mode: OpenCV background-difference motion detection (tuned for static
cams). NORMAL mode: histogram-based scene-change detection for edited video.
Frames are sampled at ~1fps for efficiency, then filtered by the chosen
detector. Each kept frame is written to frames/ as a jpg and recorded with
its source timestamp.
"""
from __future__ import annotations

from .. import config, deps


def run(job, log) -> None:
    if job.is_done("frames") and job.artifact("frames.json").exists():
        log("[frames] cached")
        return

    deps.require("cv2", "pip install opencv-python-headless")
    deps.require("numpy", "pip install numpy")
    import cv2

    meta = job.read_json("probe.json")
    detection = meta.get("detection", config.DEFAULT_DETECTION)

    cap = cv2.VideoCapture(job.source)
    if not cap.isOpened():
        raise RuntimeError(f"could not open video: {job.source}")

    fps = cap.get(cv2.CAP_PROP_FPS) or meta.get("fps") or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    # Sample ~1 frame/second — enough for CCTV and scene detection.
    step = max(1, int(round(fps)))

    log(f"[frames] mode={detection} · sampling ~1fps ({step} frame stride)")

    kept: list[dict] = []
    prev_gray = None
    prev_hist = None
    last_kept_t = -1e9
    idx = 0

    def keep(frame, t: float) -> None:
        name = f"frame_{int(round(t*1000)):09d}.jpg"
        path = job.frames_dir / name
        cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        kept.append({"file": name, "timestamp": round(t, 3)})

    while True:
        ok = cap.grab()
        if not ok:
            break
        if idx % step != 0:
            idx += 1
            continue
        ok, frame = cap.retrieve()
        if not ok:
            break
        t = idx / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if idx == 0:
            keep(frame, t)                      # always keep the opening frame
        elif detection == "cctv":
            if prev_gray is not None:
                diff = cv2.absdiff(prev_gray, gray)
                changed = float((diff > 25).mean())
                if changed > config.MOTION_THRESHOLD and \
                        (t - last_kept_t) >= config.MOTION_MIN_GAP_S:
                    keep(frame, t)
                    last_kept_t = t
        else:  # normal / scene-change
            hist = cv2.calcHist([frame], [0, 1, 2], None, [8, 8, 8],
                                [0, 256, 0, 256, 0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is not None:
                corr = cv2.compareHist(prev_hist, hist, cv2.HISTCMP_CORREL)
                if (1.0 - corr) > config.SCENE_THRESHOLD:
                    keep(frame, t)
            prev_hist = hist

        prev_gray = gray
        idx += 1

    cap.release()

    # Guarantee at least a handful of periodic frames for quiet footage.
    if len(kept) < 3 and total:
        log("[frames] low activity — adding periodic checkpoints")
        cap = cv2.VideoCapture(job.source)
        for frac in (0.25, 0.5, 0.75):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(total * frac))
            ok, frame = cap.read()
            if ok:
                keep(frame, (total * frac) / fps)
        cap.release()
        kept.sort(key=lambda k: k["timestamp"])

    job.write_json("frames.json", {"detection": detection, "frames": kept})
    log(f"[frames] {len(kept)} candidate frames extracted")
    job.mark("frames", "done")
