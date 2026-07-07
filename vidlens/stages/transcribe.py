"""TRANSCRIBE stage — faster-whisper (base int8).

Skipped when the source has no audio track (mockup: CCTV footage). Audio is
extracted to a temp wav via ffmpeg, then transcribed to timestamped segments.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .. import config, deps


def run(job, log) -> None:
    if job.is_done("transcribe") and job.artifact("transcript.json").exists():
        log("[transcribe] cached")
        return

    meta = job.read_json("probe.json")
    if not meta.get("has_audio"):
        log("[transcribe] no audio track — stage skipped")
        job.write_json("transcript.json", {"skipped": True, "segments": []})
        job.mark("transcribe", "skipped")
        return

    deps.require("faster_whisper", "pip install faster-whisper")
    ffmpeg = deps.require_binary("ffmpeg", "install ffmpeg")
    from faster_whisper import WhisperModel

    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "audio.wav"
        subprocess.run(
            [ffmpeg, "-y", "-i", job.source, "-vn", "-ac", "1",
             "-ar", "16000", str(wav)],
            capture_output=True, check=True,
        )
        log(f"[transcribe] whisper {config.WHISPER_MODEL} {config.WHISPER_COMPUTE}")
        model = WhisperModel(config.WHISPER_MODEL, compute_type=config.WHISPER_COMPUTE)
        segments, info = model.transcribe(str(wav))
        out = [{"start": round(s.start, 2), "end": round(s.end, 2),
                "text": s.text.strip()} for s in segments]

    job.write_json("transcript.json", {"skipped": False,
                                        "language": getattr(info, "language", None),
                                        "segments": out})
    log(f"[transcribe] {len(out)} segments")
    job.mark("transcribe", "done")
