"""VidLens command-line interface.

Commands:
  vidlens doctor                     check the environment
  vidlens estimate <video>           print the pre-run cost guard
  vidlens run <video> [opts]         run the full pipeline
  vidlens batch <folder> [opts]      run every video in a folder
  vidlens jobs                       list completed jobs
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, config, costs, deps, job as jobmod
from .pipeline import run as run_pipeline


def _is_url(src: str) -> bool:
    return src.startswith("http://") or src.startswith("https://")


def _make_job(args) -> jobmod.Job:
    src = args.source
    j = jobmod.Job(
        id=args.name or jobmod.new_job_id(src),
        source=src,
        is_url=_is_url(src),
        detection=args.mode,
        model=args.model,
        question=args.question or "",
        root=Path(args.root),
    )
    j.save()
    return j


# --- commands ---------------------------------------------------------------
def cmd_doctor(args) -> int:
    print("VidLens environment check\n")
    all_ok = True
    for d in deps.check_all():
        tick = "OK  " if d.ok else "MISS"
        print(f"  [{tick}] {d.name:<16} {d.detail}")
        if not d.ok:
            all_ok = False
            print(f"         -> {d.install}")
    key = "set" if _has_key() else "NOT set"
    print(f"\n  ANTHROPIC_API_KEY: {key}")
    print("\nAll good." if all_ok and _has_key()
          else "\nInstall the missing items above for full functionality.")
    return 0


def _has_key() -> bool:
    import os
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def cmd_estimate(args) -> int:
    """Estimate cost. If frames already extracted for a job, use the real
    count; otherwise estimate from duration."""
    n = args.frames
    if n is None and args.source:
        # crude: assume ~1 kept frame per 30s of footage as a planning default
        n = 142  # matches the mockup's example
        print("(no frame count given — using planning default of 142 frames)")
    est = costs.estimate(n or 0, model_key=args.model)
    print("\nCOST GUARD\n")
    print(f"  key frames        {est.key_frames}")
    print(f"  batches           {est.batches} x ~{est.frames_per_batch} frames")
    print(f"  image tokens      ~{est.image_tokens:,}")
    print(f"  transcript tokens ~{est.transcript_tokens:,}")
    print(f"  model             {est.model}")
    print(f"\n  Estimated cost:   ${est.usd:.2f}\n")
    return 0


def cmd_run(args) -> int:
    j = _make_job(args)
    print(f"Job {j.id}\n  source: {j.source}\n  mode: {j.detection} · "
          f"model: {config.MODELS[j.model]}"
          f"{' · Q: ' + j.question if j.question else ''}\n")
    if not args.yes:
        est = costs.estimate(142, model_key=j.model)  # planning estimate
        print(f"Estimated cost ~${est.usd:.2f} (planning default). "
              "Proceed? [y/N] ", end="")
        if input().strip().lower() not in ("y", "yes"):
            print("Aborted — stages cached, safe to resume later.")
            return 1
    try:
        run_pipeline(j, log=print, force=args.force)
    except deps.MissingDependency as e:
        print(f"\nMissing dependency:\n  {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"\nPipeline failed: {e}", file=sys.stderr)
        return 1
    if j.artifact("analysis.json").exists():
        a = j.read_json("analysis.json")
        print(f"\nactual cost: ${a.get('cost_usd', 0):.2f} · "
              f"{len(a.get('events', []))} events · "
              f"{a.get('flagged_count', 0)} flagged")
    print(f"open report: {j.artifact('report.html')}")
    return 0


def cmd_batch(args) -> int:
    folder = Path(args.folder)
    vids = [p for p in sorted(folder.iterdir())
            if p.suffix.lower() in config.VIDEO_EXTS]
    if not vids:
        print(f"No videos found in {folder}")
        return 1
    print(f"Batch: {len(vids)} files in {folder}\n")
    rc = 0
    for p in vids:
        args.source = str(p)
        args.name = None
        args.yes = True
        print(f"\n=== {p.name} ===")
        rc |= cmd_run(args)
    return rc


def cmd_jobs(args) -> int:
    jobs = jobmod.list_jobs(Path(args.root))
    if not jobs:
        print("No completed jobs yet.")
        return 0
    print("Completed jobs\n")
    for j in jobs:
        summary = frames = cost = ""
        if j.artifact("analysis.json").exists():
            a = j.read_json("analysis.json")
            summary = a.get("summary", "")[:70]
            cost = f"${a.get('cost_usd', 0):.2f}"
        if j.artifact("dedupe.json").exists():
            frames = f"{len(j.read_json('dedupe.json')['frames'])} frames"
        print(f"  {j.id:<28} {frames:<12} {cost:<8} {summary}")
    return 0


# --- parser -----------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vidlens",
                                description="Local video analysis pipeline.")
    p.add_argument("--version", action="version", version=f"vidlens {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--mode", choices=config.DETECTION_MODES,
                        default=config.DEFAULT_DETECTION, help="detection mode")
        sp.add_argument("--model", choices=list(config.MODELS),
                        default=config.DEFAULT_MODEL, help="claude model")
        sp.add_argument("-q", "--question", help="custom question")
        sp.add_argument("--root", default=".", help="jobs directory root")
        sp.add_argument("--name", help="explicit job id")
        sp.add_argument("--force", action="store_true", help="re-run cached stages")

    sp = sub.add_parser("doctor", help="check the environment")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("estimate", help="pre-run cost estimate")
    sp.add_argument("source", nargs="?", help="video path or URL")
    sp.add_argument("--frames", type=int, help="known key-frame count")
    sp.add_argument("--model", choices=list(config.MODELS),
                    default=config.DEFAULT_MODEL)
    sp.set_defaults(func=cmd_estimate)

    sp = sub.add_parser("run", help="run the full pipeline on one video")
    sp.add_argument("source", help="video path or YouTube URL")
    sp.add_argument("-y", "--yes", action="store_true", help="skip cost prompt")
    common(sp)
    sp.set_defaults(func=cmd_run)

    sp = sub.add_parser("batch", help="run every video in a folder")
    sp.add_argument("folder", help="folder of videos")
    common(sp)
    sp.set_defaults(func=cmd_batch)

    sp = sub.add_parser("jobs", help="list completed jobs")
    sp.add_argument("--root", default=".", help="jobs directory root")
    sp.set_defaults(func=cmd_jobs)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
