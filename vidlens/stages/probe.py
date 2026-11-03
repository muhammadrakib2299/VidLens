"""PROBE stage — ffprobe metadata + detection-mode auto-selection."""
from __future__ import annotations

import json
import subprocess

from .. import deps
from ..util import human_size


def _ffprobe(path: str) -> dict:
    ffprobe = deps.require_binary("ffprobe", "install ffmpeg (bundles ffprobe)")
    cmd = [
        ffprobe, "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", path,
    ]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def run(job, log) -> None:
    if job.is_done("probe") and job.artifact("probe.json").exists():
        log("[probe] cached")
        return

    raw = _ffprobe(job.source)
    fmt = raw.get("format", {})
    streams = raw.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration = float(fmt.get("duration", 0) or video.get("duration", 0) or 0)
    width = int(video.get("width", 0) or 0)
    height = int(video.get("height", 0) or 0)
    size = int(fmt.get("size", 0) or 0)
    has_audio = audio is not None

    # Auto-detect CCTV vs normal: no audio track -> almost always static CCTV.
    detection = job.detection
    if detection == "auto":
        detection = "cctv" if not has_audio else "normal"
        job.detection = detection

    meta = {
        "duration_s": duration,
        "width": width,
        "height": height,
        "size_bytes": size,
        "size_human": human_size(size),
        "has_audio": has_audio,
        "detection": detection,
        "fps": _fps(video),
    }
    job.write_json("probe.json", meta)
    log(f"[probe] {int(duration//60)}:{int(duration%60):02d} · {width}x{height} · "
        f"{meta['size_human']} · audio={'yes' if has_audio else 'none'} "
        f"-> mode={detection}")
    job.mark("probe", "done")


def _fps(video: dict) -> float:
    rate = video.get("avg_frame_rate") or video.get("r_frame_rate") or "0/1"
    try:
        num, den = rate.split("/")
        den = float(den)
        return float(num) / den if den else 0.0
    except Exception:
        return 0.0
