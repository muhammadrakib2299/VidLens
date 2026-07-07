"""ANALYZE stage — Claude vision analysis of the key frames.

Key frames are downsampled and sent to Claude in batches (~18 frames, as in
the mockup). For each batch the model returns structured JSON events with a
timestamp, title, description, and an "unusual activity" flag. A final pass
merges the timeline into a summary and answers the optional custom question.

Uses the official Anthropic SDK with structured outputs so the response is
guaranteed-parseable JSON. Model is haiku by default, sonnet for hard cases.
"""
from __future__ import annotations

import base64
import io
import json

from .. import config, costs, deps
from ..util import fmt_ts, parse_ts

_EVENTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "timestamp": {"type": "string",
                                  "description": "HH:MM:SS of one supplied frame"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "flagged": {"type": "boolean",
                                "description": "true if unusual / noteworthy"},
                    "reason": {"type": "string",
                               "description": "why flagged, else empty"},
                },
                "required": ["timestamp", "title", "description",
                             "flagged", "reason"],
            },
        }
    },
    "required": ["events"],
}

_SUMMARY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "custom_answer": {"type": "string",
                          "description": "answer to the custom question, or empty"},
    },
    "required": ["summary", "custom_answer"],
}


def _encode_frame(path) -> str:
    from PIL import Image
    with Image.open(path) as im:
        im = im.convert("RGB")
        long_edge = max(im.size)
        if long_edge > config.FRAME_MAX_EDGE:
            scale = config.FRAME_MAX_EDGE / long_edge
            im = im.resize((int(im.width * scale), int(im.height * scale)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


def _batches(frames, n):
    for i in range(0, len(frames), n):
        yield frames[i:i + n]


def run(job, log) -> None:
    if job.is_done("analyze") and job.artifact("analysis.json").exists():
        log("[analyze] cached")
        return

    deps.require("anthropic", "pip install anthropic")
    deps.require("PIL", "pip install pillow")
    import anthropic

    frames = job.read_json("dedupe.json")["frames"]
    transcript = job.read_json("transcript.json") if \
        job.artifact("transcript.json").exists() else {"segments": []}
    model_id = config.MODELS[job.model]

    try:
        client = anthropic.Anthropic()
    except Exception as e:                       # missing key etc.
        raise deps.MissingDependency(
            "could not init Anthropic client (is ANTHROPIC_API_KEY set?): "
            f"{e}"
        )

    mode = job.detection
    question = job.question.strip()
    q_line = (f'\nAlso specifically look for and report on this custom '
              f'question: "{question}".' if question else "")

    system = (
        "You are VidLens, a video-analysis assistant. You are given key frames "
        "from surveillance or normal video, each labelled with its timestamp. "
        "Identify distinct events: people, vehicles, animals, and any unusual "
        "activity. Report each event once, using the timestamp of the frame it "
        "is clearest in. Flag anything that looks unusual for the setting "
        "(loitering, forced entry, unexpected presence). Be concise and factual."
    )

    all_events: list[dict] = []
    total_in = total_out = 0
    batch_list = list(_batches(frames, config.FRAMES_PER_BATCH))

    for bi, batch in enumerate(batch_list, 1):
        content = [{
            "type": "text",
            "text": (f"Detection mode: {mode}. Analyze these "
                     f"{len(batch)} frames (batch {bi}/{len(batch_list)})."
                     f"{q_line}"),
        }]
        for fr in batch:
            content.append({"type": "text", "text": f"Frame at {fmt_ts(fr['timestamp'])}:"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg",
                           "data": _encode_frame(job.frames_dir / fr["file"])},
            })

        resp = client.messages.create(
            model=model_id,
            max_tokens=config.ANALYZE_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"format": {"type": "json_schema", "schema": _EVENTS_SCHEMA}},
        )
        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        text = next((b.text for b in resp.content if b.type == "text"), "{}")
        events = json.loads(text).get("events", [])
        flagged_n = sum(1 for e in events if e.get("flagged"))
        note = f" — {flagged_n} flagged" if flagged_n else ""
        log(f"[analyze] batch {bi}/{len(batch_list)} -> {len(events)} events{note}")
        all_events.extend(events)

    # Normalise + sort by timestamp
    for e in all_events:
        e["_t"] = parse_ts(e.get("timestamp", "0"))
    all_events.sort(key=lambda e: e["_t"])
    for e in all_events:
        e.pop("_t", None)

    # --- summary pass -------------------------------------------------------
    timeline_txt = "\n".join(
        f"- {e['timestamp']} {e['title']}: {e['description']}"
        f"{'  [FLAGGED: ' + e['reason'] + ']' if e.get('flagged') else ''}"
        for e in all_events
    ) or "(no events detected)"
    transcript_txt = " ".join(s["text"] for s in transcript.get("segments", []))[:4000]

    summary_user = (
        f"Here is the event timeline extracted from the video:\n{timeline_txt}\n\n"
        + (f"Audio transcript excerpt:\n{transcript_txt}\n\n" if transcript_txt else "")
        + "Write a short factual summary (2-4 sentences) of what happens in the "
          "footage, mentioning flagged events by timestamp."
        + (f' Then answer this custom question in custom_answer: "{question}".'
           if question else " Leave custom_answer empty.")
    )
    sresp = client.messages.create(
        model=model_id,
        max_tokens=1024,
        messages=[{"role": "user", "content": summary_user}],
        output_config={"format": {"type": "json_schema", "schema": _SUMMARY_SCHEMA}},
    )
    total_in += sresp.usage.input_tokens
    total_out += sresp.usage.output_tokens
    stext = next((b.text for b in sresp.content if b.type == "text"), "{}")
    sdata = json.loads(stext)

    analysis = {
        "model": model_id,
        "detection": mode,
        "question": question,
        "summary": sdata.get("summary", ""),
        "custom_answer": sdata.get("custom_answer", ""),
        "events": all_events,
        "flagged_count": sum(1 for e in all_events if e.get("flagged")),
        "usage": {"input_tokens": total_in, "output_tokens": total_out},
        "cost_usd": costs.actual_cost(total_in, total_out, model_id),
    }
    job.write_json("analysis.json", analysis)
    log(f"[analyze] done — {len(all_events)} events, "
        f"{analysis['flagged_count']} flagged, "
        f"${analysis['cost_usd']:.2f} actual")
    job.mark("analyze", "done")
