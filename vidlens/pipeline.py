"""Pipeline orchestrator — runs stages in order with resume support.

Each stage writes its artifacts and marks itself done/skipped in the job
manifest, so re-running a job picks up where it left off (the mockup's
"stages cached to disk — safe to interrupt and resume").
"""
from __future__ import annotations

from . import config
from .stages import download, probe, frames, dedupe, transcribe, analyze, report

# Stage name -> module. Order defined by config.STAGE_DEFS.
_STAGES = {
    "download": download,
    "probe": probe,
    "frames": frames,
    "dedupe": dedupe,
    "transcribe": transcribe,
    "analyze": analyze,
    "report": report,
}


def run(job, log=print, force: bool = False) -> None:
    log(f"[start] job {job.id}")
    for name, _detail in config.STAGE_DEFS:
        if not force and job.is_done(name):
            log(f"[{name}] already complete — skipping (use --force to redo)")
            continue
        try:
            _STAGES[name].run(job, log)
        except Exception as e:
            job.mark(name, "error")
            log(f"[{name}] ERROR: {e}")
            raise
    log(f"[done] report ready -> {job.artifact('report.html')}")
