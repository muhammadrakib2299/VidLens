"""DEDUPE stage — drop near-duplicate frames by perceptual hash.

Keeps a frame only if its phash is at least PHASH_DISTANCE hamming bits away
from every already-kept frame (mockup: "phash distance < 6 — dropped dupes").
"""
from __future__ import annotations

from .. import config, deps


def run(job, log) -> None:
    if job.is_done("dedupe") and job.artifact("dedupe.json").exists():
        log("[dedupe] cached")
        return

    deps.require("PIL", "pip install pillow")
    deps.require("imagehash", "pip install imagehash")
    from PIL import Image
    import imagehash

    frames = job.read_json("frames.json")["frames"]
    kept: list[dict] = []
    hashes: list = []

    for fr in frames:
        path = job.frames_dir / fr["file"]
        try:
            with Image.open(path) as im:
                h = imagehash.phash(im)
        except Exception:
            continue
        if all((h - kh) >= config.PHASH_DISTANCE for kh in hashes):
            kept.append(fr)
            hashes.append(h)

    dropped = len(frames) - len(kept)
    job.write_json("dedupe.json", {"frames": kept})
    log(f"[dedupe] phash distance < {config.PHASH_DISTANCE} — dropped "
        f"{dropped} near-duplicates, {len(kept)} key frames kept")
    job.mark("dedupe", "done")
