"""Static configuration: models, pricing, thresholds, stage order.

Mirrors the values shown in the VidLens design mockups (STAGE_DEFS,
detection modes, model choices) so the CLI behaves like the UI describes.
"""
from __future__ import annotations

# --- Models -----------------------------------------------------------------
# The mockup labels these "claude-haiku" (default) and "claude-sonnet"
# (hard cases). Mapped to current model IDs.
MODELS = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-5",
}
DEFAULT_MODEL = "haiku"

# USD per single token (input, output). Divide the per-1M price by 1e6.
# Haiku 4.5: $1.00 / $5.00 per 1M.  Sonnet 5: $3.00 / $15.00 per 1M.
PRICING = {
    "claude-haiku-4-5": {"input": 1.00 / 1e6, "output": 5.00 / 1e6},
    "claude-sonnet-5": {"input": 3.00 / 1e6, "output": 15.00 / 1e6},
}

# Rough token cost of one downsampled frame at <=1568px long edge.
IMAGE_TOKENS = 1600

# --- Pipeline stages (name, detail) in execution order ----------------------
STAGE_DEFS = [
    ("download", "yt-dlp (skipped for local files)"),
    ("probe", "ffprobe"),
    ("frames", "motion / scene detect"),
    ("dedupe", "phash"),
    ("transcribe", "whisper (skipped when no audio)"),
    ("analyze", "claude api"),
    ("report", "report.md + report.html"),
]

# --- Detection ---------------------------------------------------------------
DETECTION_MODES = ("auto", "cctv", "normal")
DEFAULT_DETECTION = "auto"

# CCTV motion detection (OpenCV background diff)
MOTION_THRESHOLD = 0.32      # fraction-of-frame change to count as motion
MOTION_MIN_GAP_S = 1.0       # min seconds between kept motion frames
# NORMAL scene-change detection
SCENE_THRESHOLD = 0.40       # histogram-correlation distance to call a new scene
# AUTO: files with no audio track and low average motion look like CCTV
AUTO_CCTV_MAX_AUDIO = False  # no audio -> lean CCTV

# --- Dedupe ------------------------------------------------------------------
PHASH_DISTANCE = 6           # hamming distance below which frames are dupes

# --- Analyze -----------------------------------------------------------------
FRAMES_PER_BATCH = 18        # frames sent to Claude per request (mockup: ~18)
FRAME_MAX_EDGE = 1568        # downsample long edge before upload
ANALYZE_MAX_TOKENS = 4096

# --- Transcribe --------------------------------------------------------------
WHISPER_MODEL = "base"       # faster-whisper size (mockup: "base int8")
WHISPER_COMPUTE = "int8"

# --- Jobs --------------------------------------------------------------------
JOBS_DIR = "jobs"
VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".dav", ".mov", ".m4v", ".webm")
