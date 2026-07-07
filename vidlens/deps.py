"""Dependency detection and friendly error messages.

Heavy deps (opencv, faster-whisper, yt-dlp, anthropic) and external binaries
(ffmpeg/ffprobe) are optional and imported lazily by the stage that needs
them. `vidlens doctor` reports what is present so the user can install only
what their workflow requires.
"""
from __future__ import annotations

import importlib.util
import shutil
from dataclasses import dataclass


@dataclass
class DepStatus:
    name: str
    ok: bool
    detail: str
    install: str


def _has_module(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def _binary(name: str) -> str | None:
    return shutil.which(name)


def check_all() -> list[DepStatus]:
    out: list[DepStatus] = []

    ff = _binary("ffmpeg")
    out.append(DepStatus("ffmpeg", bool(ff), ff or "not found",
                         "https://ffmpeg.org/download.html (add to PATH)"))
    fp = _binary("ffprobe")
    out.append(DepStatus("ffprobe", bool(fp), fp or "not found",
                         "ships with ffmpeg"))

    checks = [
        ("numpy", "numpy", "pip install numpy"),
        ("pillow", "PIL", "pip install pillow"),
        ("opencv", "cv2", "pip install opencv-python-headless"),
        ("imagehash", "imagehash", "pip install imagehash"),
        ("faster-whisper", "faster_whisper", "pip install faster-whisper"),
        ("yt-dlp", "yt_dlp", "pip install yt-dlp"),
        ("anthropic", "anthropic", "pip install anthropic"),
    ]
    for label, mod, install in checks:
        ok = _has_module(mod)
        out.append(DepStatus(label, ok, "installed" if ok else "missing", install))
    return out


class MissingDependency(RuntimeError):
    """Raised when a stage needs a dependency that is not installed."""


def require(module: str, install_hint: str) -> None:
    if not _has_module(module):
        raise MissingDependency(
            f"required dependency '{module}' is not installed.\n"
            f"  install it with:  {install_hint}"
        )


def require_binary(name: str, install_hint: str) -> str:
    path = _binary(name)
    if not path:
        raise MissingDependency(
            f"required binary '{name}' was not found on PATH.\n"
            f"  install it: {install_hint}"
        )
    return path
