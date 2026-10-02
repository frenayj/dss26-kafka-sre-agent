"""The run metrics must carry real model latency and cache writes, not Strands' zeros."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agent import models


def test_each_model_call_is_timed(monkeypatch):
    async def fake_stream(self, *args, **kwargs):
        yield {"contentBlockDelta": {"delta": {"text": "ok"}}}
        await asyncio.sleep(0.05)
        yield {"metadata": {"usage": {"inputTokens": 1}, "metrics": {"latencyMs": 0}}}

    monkeypatch.setattr(models.OpenAIModel, "stream", fake_stream)
    model = models.build_model("claude")

    async def collect():
        return [e async for e in model.stream([])]

    events = asyncio.run(collect())
    assert events[0] == {"contentBlockDelta": {"delta": {"text": "ok"}}}
    assert events[1]["metadata"]["metrics"]["latencyMs"] >= 40
    assert events[1]["metadata"]["usage"] == {"inputTokens": 1}


def _usage(**details):
    return SimpleNamespace(
        prompt_tokens=11047,
        completion_tokens=5,
        total_tokens=11052,
        prompt_tokens_details=SimpleNamespace(cached_tokens=0, **details),
    )


def test_cache_writes_are_read_under_the_gateways_name():
    """The gateway reports Anthropic's cache writes as cache_creation_tokens."""
    model = models.build_model("claude")
    chunk = model.format_chunk({"chunk_type": "metadata", "data": _usage(cache_creation_tokens=11044)})
    usage = chunk["metadata"]["usage"]
    assert usage["inputTokens"] == 11047  # cached and written tokens included
    assert usage["cacheWriteInputTokens"] == 11044


def test_a_call_without_cache_writes_reports_none():
    model = models.build_model("claude")
    usage = model.format_chunk({"chunk_type": "metadata", "data": _usage()})["metadata"]["usage"]
    assert "cacheWriteInputTokens" not in usage
