"""Offline cost estimation for the pre-run cost guard.

Deliberately does NOT call the API — the whole point of the mockup's Cost
Guard is to estimate spend *before* committing to a run.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import config


@dataclass
class Estimate:
    key_frames: int
    batches: int
    frames_per_batch: int
    image_tokens: int
    prompt_tokens: int
    transcript_tokens: int
    output_tokens: int
    model: str
    usd: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def estimate(
    key_frames: int,
    model_key: str = config.DEFAULT_MODEL,
    transcript_tokens: int = 0,
    per_batch: int = config.FRAMES_PER_BATCH,
) -> Estimate:
    model_id = config.MODELS[model_key]
    price = config.PRICING[model_id]

    batches = max(1, math.ceil(key_frames / per_batch)) if key_frames else 0

    image_tokens = key_frames * config.IMAGE_TOKENS
    # ~350 tokens of instruction/timestamps per batch, resent each request.
    prompt_tokens = batches * 350
    # ~250 output tokens per batch of structured events + one summary pass.
    output_tokens = batches * 250 + 400

    input_tokens = image_tokens + prompt_tokens + transcript_tokens
    usd = input_tokens * price["input"] + output_tokens * price["output"]

    return Estimate(
        key_frames=key_frames,
        batches=batches,
        frames_per_batch=per_batch,
        image_tokens=image_tokens,
        prompt_tokens=prompt_tokens,
        transcript_tokens=transcript_tokens,
        output_tokens=output_tokens,
        model=model_id,
        usd=round(usd, 4),
    )


def actual_cost(usage_in: int, usage_out: int, model_id: str) -> float:
    price = config.PRICING[model_id]
    return round(usage_in * price["input"] + usage_out * price["output"], 4)
