"""REPORT stage — merge analysis into report.md and a static report.html.

report.html reuses the VidLens visual language (Space Grotesk / IBM Plex Mono,
amber accent) as a self-contained static page — no runtime required. Frames
are embedded from the frames/ directory so the report is portable.
"""
from __future__ import annotations

import base64
import html
from pathlib import Path

from ..util import fmt_ts


# ---------------------------------------------------------------------------
def _load(job):
    meta = job.read_json("probe.json")
    analysis = job.read_json("analysis.json")
    return meta, analysis


def _write_markdown(job, meta, analysis) -> None:
    dur = fmt_ts(meta.get("duration_s", 0))
    lines = [
        f"# VidLens report — {Path(job.source).name}",
        "",
        f"- **Duration:** {dur}",
        f"- **Mode:** {analysis.get('detection')}",
        f"- **Resolution:** {meta.get('width')}x{meta.get('height')}",
        f"- **Audio:** {'yes' if meta.get('has_audio') else 'none'}",
        f"- **Model:** {analysis.get('model')}",
        f"- **Cost:** ${analysis.get('cost_usd', 0):.2f}",
        "",
        "## Summary",
        "",
        analysis.get("summary", "").strip() or "_(none)_",
        "",
    ]
    if analysis.get("question"):
        lines += ["## Custom question", "",
                  f"**Q:** {analysis['question']}", "",
                  f"**A:** {analysis.get('custom_answer') or '_(no answer)_'}", ""]

    flagged = [e for e in analysis.get("events", []) if e.get("flagged")]
    lines += [f"## Flagged — {len(flagged)}", ""]
    if flagged:
        for e in flagged:
            lines.append(f"- **{e['timestamp']}** {e['title']} — {e.get('reason','')}")
    else:
        lines.append("_None._")
    lines.append("")

    lines += ["## Event timeline", ""]
    for e in analysis.get("events", []):
        mark = " ⚑" if e.get("flagged") else ""
        lines.append(f"- **{e['timestamp']}**{mark} {e['title']} — {e['description']}")
    lines.append("")

    job.artifact("report.md").write_text("\n".join(lines), encoding="utf-8")


def _b64_frame(job, ts: float) -> str | None:
    """Best-effort embed of the nearest extracted frame for a timestamp."""
    frames = job.read_json("dedupe.json")["frames"]
    if not frames:
        return None
    nearest = min(frames, key=lambda f: abs(f["timestamp"] - ts))
    path = job.frames_dir / nearest["file"]
    if not path.exists():
        return None
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{data}"


_CSS = """
html,body{margin:0;padding:0;background:#F5F4EF;font-family:'Space Grotesk',system-ui,sans-serif;color:#1A1D23;}
a{color:#B26A0F;text-decoration:none;} a:hover{color:#D08A1E;}
.mono{font-family:'IBM Plex Mono',ui-monospace,monospace;}
.wrap{max-width:960px;margin:0 auto;padding:40px;}
.header{border-bottom:1px solid #E4E1D8;background:#FFFFFF;}
.kicker{font-size:11px;color:#B26A0F;letter-spacing:.15em;margin-bottom:8px;}
h1{margin:0 0 20px;font-size:30px;font-weight:600;letter-spacing:-.01em;}
.meta{display:flex;flex-wrap:wrap;gap:28px;font-size:11px;color:#9A9484;}
.meta b{color:#1A1D23;font-weight:500;}
.grid{display:grid;grid-template-columns:2fr 1fr;gap:24px;margin-bottom:48px;}
.card{background:#FFFFFF;border:1px solid #E4E1D8;padding:28px;}
.card .label{font-size:11px;color:#9A9484;letter-spacing:.15em;margin-bottom:14px;}
.flag{background:#FDF3E0;border:1px solid #EBCF94;}
.flag .label{color:#B26A0F;}
.section-label{font-size:11px;color:#9A9484;letter-spacing:.15em;margin-bottom:20px;}
.ev{display:grid;grid-template-columns:120px 1fr 160px;gap:20px;align-items:center;
    padding:16px 20px;background:#FFFFFF;border-left:2px solid #E4E1D8;margin-bottom:2px;}
.ev.flag{background:#FDF3E0;border-left-color:#E8A33D;}
.ev .ts{font-size:13px;}
.ev .title{font-size:14px;margin-bottom:3px;}
.ev .desc{font-size:12px;color:#6E6A5E;line-height:1.5;}
.ev img{width:160px;height:90px;object-fit:cover;border:1px solid #E4E1D8;}
p{line-height:1.7;color:#40454F;}
@media(max-width:720px){.grid{grid-template-columns:1fr;}.ev{grid-template-columns:1fr;}.ev img{width:100%;}}
"""


def _esc(s) -> str:
    return html.escape(str(s or ""))


def _write_html(job, meta, analysis) -> None:
    dur = fmt_ts(meta.get("duration_s", 0))
    events = analysis.get("events", [])
    flagged = [e for e in events if e.get("flagged")]

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>VidLens report — {_esc(Path(job.source).name)}</title>",
        "<link rel='preconnect' href='https://fonts.googleapis.com'>",
        "<link href='https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap' rel='stylesheet'>",
        f"<style>{_CSS}</style></head><body>",
        "<div class='header'><div class='wrap' style='padding:36px 40px;'>",
        "<div class='kicker mono'>ANALYSIS REPORT</div>",
        f"<h1>{_esc(Path(job.source).name)}</h1>",
        "<div class='meta mono'>",
        f"<div>DURATION <b>{dur}</b></div>",
        f"<div>MODE <b>{_esc(analysis.get('detection'))}</b></div>",
        f"<div>RESOLUTION <b>{meta.get('width')}x{meta.get('height')}</b></div>",
        f"<div>AUDIO <b>{'yes' if meta.get('has_audio') else 'none'}</b></div>",
        f"<div>MODEL <b>{_esc(analysis.get('model'))}</b></div>",
        f"<div>COST <b style='color:#B26A0F'>${analysis.get('cost_usd',0):.2f}</b></div>",
        "</div></div></div>",
        "<div class='wrap'>",
        "<div class='grid'>",
        "<div class='card'><div class='label mono'>SUMMARY</div>",
        f"<p>{_esc(analysis.get('summary'))}</p>",
    ]
    if analysis.get("question"):
        parts.append(
            f"<p><b>{_esc(analysis['question'])}</b><br>"
            f"{_esc(analysis.get('custom_answer') or '(no answer)')}</p>")
    parts.append("</div>")

    parts.append(f"<div class='card flag'><div class='label mono'>&#9873; FLAGGED — {len(flagged)}</div>")
    if flagged:
        for e in flagged:
            parts.append(
                f"<div class='mono' style='font-size:13px;color:#B26A0F;margin-bottom:6px;'>{_esc(e['timestamp'])}</div>"
                f"<div style='font-size:13px;color:#6B5836;line-height:1.6;margin-bottom:12px;'>{_esc(e.get('reason') or e.get('description'))}</div>")
    else:
        parts.append("<div style='font-size:13px;color:#6B5836;'>No unusual activity flagged.</div>")
    parts.append("</div></div>")

    parts.append("<div class='section-label mono'>EVENT TIMELINE</div>")
    for e in events:
        img = _b64_frame(job, _ts(e))
        cls = "ev flag" if e.get("flagged") else "ev"
        thumb = (f"<img src='{img}' alt='frame'>" if img
                 else "<div class='mono' style='width:160px;height:90px;background:linear-gradient(135deg,#EFEDE6,#F7F6F1);border:1px solid #E4E1D8;display:grid;place-items:center;font-size:10px;color:#A8A395;'>no frame</div>")
        parts.append(
            f"<div class='{cls}'>"
            f"<div class='ts mono' style='color:{'#B26A0F' if e.get('flagged') else '#9A9484'}'>{_esc(e['timestamp'])}</div>"
            f"<div><div class='title'>{_esc(e['title'])}</div>"
            f"<div class='desc'>{_esc(e['description'])}</div></div>"
            f"{thumb}</div>")

    parts.append("</div></body></html>")
    job.artifact("report.html").write_text("".join(parts), encoding="utf-8")


def _ts(event) -> float:
    from ..util import parse_ts
    return parse_ts(event.get("timestamp", "0"))


def run(job, log) -> None:
    meta, analysis = _load(job)
    _write_markdown(job, meta, analysis)
    _write_html(job, meta, analysis)
    log("[report] merging timeline + summary -> report.md, report.html")
    log(f"[done] job complete — cached to {job.dir}")
    job.mark("report", "done")
