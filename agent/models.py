"""Model factory: every agent talks to the LiteLLM gateway.

The agent never imports a provider SDK or names a provider model.
``build_model`` returns a Strands ``OpenAIModel`` pointed at the gateway's
OpenAI-compatible endpoint, with a gateway *alias* (``claude``,
``claude-haiku``, ``mistral-medium``, ...) as the model id. The gateway maps
the alias to a provider model in ``agent/gateway/litellm.yaml``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from strands.models.openai import OpenAIModel

from agent.config import LLM_GATEWAY_API_KEY, LLM_GATEWAY_URL

# The gateway's routing table, as copied into this image. After changing it,
# `make agent-up` as well as `make gateway-up`, or traces name the old model.
GATEWAY_CONFIG = Path(__file__).resolve().parent / "gateway" / "litellm.yaml"


@dataclass(frozen=True)
class GatewayModel:
    """What a gateway alias routes to, e.g. ``anthropic`` / ``claude-sonnet-5-5``."""

    provider: str
    model: str


@lru_cache(maxsize=1)
def gateway_models() -> dict[str, GatewayModel]:
    """Each gateway alias's provider model, from litellm.yaml (empty if unreadable)."""
    try:
        config = yaml.safe_load(GATEWAY_CONFIG.read_text()) or {}
    except (OSError, yaml.YAMLError):
        return {}
    models: dict[str, GatewayModel] = {}
    for entry in config.get("model_list") or []:
        alias = entry.get("model_name")
        target = (entry.get("litellm_params") or {}).get("model")
        if isinstance(alias, str) and isinstance(target, str):
            provider, _, model = target.partition("/")
            models[alias] = GatewayModel(provider, model) if model else GatewayModel("", provider)
    return models


class TimedOpenAIModel(OpenAIModel):
    """``OpenAIModel`` that reports each model call's latency and cache writes.

    Strands' OpenAI provider reports every call's ``latencyMs`` as 0, so the
    run metrics - and the dashboard's "model" time - would always read 0ms.
    The usage chunk arrives last, so stamping the elapsed time on it measures
    the whole call; Strands then accumulates it per agent.

    It also reads cache writes only under OpenAI's name for them
    (``prompt_tokens_details.cache_write_tokens``). The gateway reports
    Anthropic's as ``cache_creation_tokens``, so without this every write
    reads 0 and is priced as plain input instead of at the write rate.
    """

    def format_chunk(self, event: dict[str, Any], **kwargs: Any) -> Any:
        chunk = super().format_chunk(event, **kwargs)
        if event.get("chunk_type") == "metadata":
            usage = chunk["metadata"]["usage"]
            details = getattr(event.get("data"), "prompt_tokens_details", None)
            written = getattr(details, "cache_creation_tokens", None)
            if isinstance(written, int) and "cacheWriteInputTokens" not in usage:
                usage["cacheWriteInputTokens"] = written
        return chunk

    async def stream(self, *args, **kwargs):
        start = time.perf_counter()
        async for event in super().stream(*args, **kwargs):
            metadata = event.get("metadata") if isinstance(event, dict) else None
            if isinstance(metadata, dict):
                metrics = metadata.setdefault("metrics", {})
                if not metrics.get("latencyMs"):
                    metrics["latencyMs"] = int((time.perf_counter() - start) * 1000)
            yield event


def build_model(model_alias: str, *, max_tokens: int = 8192) -> OpenAIModel:
    """A Strands model that sends ``model_alias`` to the gateway.

    ``max_tokens`` caps one response. A cap is not a cost - only generated
    tokens are billed - but a reply that hits it is cut off mid-call, and
    diagnosis's structured findings need more than 4096.
    """
    return TimedOpenAIModel(
        client_args={"api_key": LLM_GATEWAY_API_KEY, "base_url": LLM_GATEWAY_URL},
        model_id=model_alias,
        params={"max_tokens": max_tokens},
    )
