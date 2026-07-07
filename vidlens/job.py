"""Job model and on-disk layout.

A job lives in ./jobs/<id>/ and holds per-stage cached artifacts so an
interrupted run is safe to resume (the mockup's "stages cached to disk").

Layout:
  jobs/<id>/
    manifest.json      # job config + status of each stage
    source/            # downloaded video (URL jobs only)
    frames/            # extracted key frames as jpg
    probe.json         # ffprobe metadata
    frames.json        # frame list (path, timestamp)
    dedupe.json        # kept key frames after phash
    transcript.json    # whisper segments (or {skipped:true})
    analysis.json      # merged events + summary from Claude
    report.md
    report.html
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def new_job_id(source: str) -> str:
    """e.g. 2026-07-06_cctv01 style — date + source stem."""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    stem = Path(source).stem or "job"
    stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)[:32]
    return f"{date}_{stem}"


@dataclass
class Job:
    id: str
    source: str                 # local path or URL
    is_url: bool
    detection: str = config.DEFAULT_DETECTION
    model: str = config.DEFAULT_MODEL
    question: str = ""
    root: Path = field(default=Path("."))
    stages: dict = field(default_factory=dict)   # name -> {status, at}
    created_at: str = field(default_factory=_now_iso)

    # ---- paths -------------------------------------------------------------
    @property
    def dir(self) -> Path:
        return self.root / config.JOBS_DIR / self.id

    @property
    def frames_dir(self) -> Path:
        return self.dir / "frames"

    @property
    def source_dir(self) -> Path:
        return self.dir / "source"

    def artifact(self, name: str) -> Path:
        return self.dir / name

    # ---- lifecycle ---------------------------------------------------------
    def ensure_dirs(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir.mkdir(exist_ok=True)

    def mark(self, stage: str, status: str) -> None:
        self.stages[stage] = {"status": status, "at": _now_iso()}
        self.save()

    def status_of(self, stage: str) -> str:
        return self.stages.get(stage, {}).get("status", "pending")

    def is_done(self, stage: str) -> bool:
        return self.status_of(stage) in ("done", "skipped")

    # ---- persistence -------------------------------------------------------
    def save(self) -> None:
        self.ensure_dirs()
        data = asdict(self)
        data["root"] = str(self.root)
        with open(self.dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, job_dir: Path) -> "Job":
        with open(Path(job_dir) / "manifest.json", encoding="utf-8") as f:
            data = json.load(f)
        data["root"] = Path(data.get("root", "."))
        return cls(**data)

    def write_json(self, name: str, obj) -> None:
        with open(self.artifact(name), "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=2)

    def read_json(self, name: str):
        with open(self.artifact(name), encoding="utf-8") as f:
            return json.load(f)


def list_jobs(root: Path) -> list["Job"]:
    base = Path(root) / config.JOBS_DIR
    if not base.exists():
        return []
    jobs = []
    for d in sorted(base.iterdir(), reverse=True):
        if (d / "manifest.json").exists():
            try:
                jobs.append(Job.load(d))
            except Exception:
                continue
    return jobs
