"""DOWNLOAD stage — fetch a YouTube/remote video with yt-dlp.

Skipped for local files. Sets job.source to the downloaded path on success.
"""
from __future__ import annotations

from pathlib import Path

from .. import deps


def run(job, log) -> None:
    if not job.is_url:
        log("[download] local file — stage skipped")
        job.mark("download", "skipped")
        return

    deps.require("yt_dlp", "pip install yt-dlp")
    import yt_dlp  # noqa: E402

    job.source_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(job.source_dir / "%(id)s.%(ext)s")
    log(f"[download] fetching {job.source}")

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(job.source, download=True)
        path = Path(ydl.prepare_filename(info))
        # merge_output_format may rewrite the extension
        if not path.exists():
            cand = list(job.source_dir.glob(f"{info.get('id','')}*"))
            path = cand[0] if cand else path

    log(f"[download] saved -> {path.name}")
    job.source = str(path)
    job.is_url = False   # downstream stages now treat it as a local file
    job.mark("download", "done")
