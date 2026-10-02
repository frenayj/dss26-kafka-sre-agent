"""OpenTelemetry tracing for agent runs, exported to Phoenix over OTLP/HTTP.

Strands already emits a span for every agent turn, model call and tool call.
This module adds what Phoenix needs to make those spans useful:

* **OpenInference content.** Strands records prompts, completions and tool
  arguments as span *events*; Phoenix's INPUT/OUTPUT panels read the
  OpenInference span *attributes*. ``StrandsAgentsToOpenInferenceProcessor``
  translates one into the other.
* **One trace per run.** ``run_context`` opens a root span and stamps the run
  and incident ids onto every span created inside it (including Strands'),
  so a run can be found in Phoenix by its id from the dashboard.
* **The model, not the alias.** Strands only knows the gateway alias
  (``claude``); the span names the model and vendor the gateway routes it to
  (``claude-sonnet-5-5``, ``anthropic``), read from agent/gateway/litellm.yaml.
* **Cached tokens counted once.** The gateway's input count already includes
  cached tokens; the OpenInference processor adds them again, so Phoenix
  would bill every cached token twice, once at the full input rate.

Everything is best effort: an unreachable collector costs traces, never a run.
Set ``OTEL_SDK_DISABLED=true`` to switch tracing off entirely (the tests do).
"""

from __future__ import annotations

import contextlib
import contextvars
import json
import os
from dataclasses import dataclass
from typing import Any, Iterator, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from agent.models import gateway_models

# Phoenix's published port, for a host run; compose points the agent
# container at the in-network service with OTEL_EXPORTER_OTLP_ENDPOINT.
DEFAULT_ENDPOINT = f"http://localhost:{os.environ.get('HOST_PORT_PHOENIX') or '6006'}"

# OpenInference attribute names (github.com/Arize-ai/openinference).
OI_SPAN_KIND = "openinference.span.kind"
OI_LLM_PROVIDER = "llm.provider"
OI_TAGS = "tag.tags"  # list[str], not a JSON string
OI_METADATA = "metadata"  # JSON string
OI_PROJECT_NAME = "openinference.project.name"  # resource attribute

ATTR_RUN_ID = "run.id"
ATTR_INCIDENT_ID = "incident.id"
ATTR_SESSION_ID = "session.id"  # also OpenInference's session attribute
ATTR_AGENT_VERSION = "agent.version"
# The model Strands asked for; OpenInference copies it to llm.model_name.
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GATEWAY_ALIAS = "llm.gateway_alias"
# A model call's token counts, as Strands records them.
GEN_AI_INPUT_TOKENS = ("gen_ai.usage.input_tokens", "gen_ai.usage.prompt_tokens")
GEN_AI_CACHED_TOKENS = ("gen_ai.usage.cache_read_input_tokens", "gen_ai.usage.cache_write_input_tokens")


@dataclass(frozen=True)
class RunIds:
    run_id: str
    incident_id: str
    agent_version: str


_CURRENT_RUN: contextvars.ContextVar[Optional[RunIds]] = contextvars.ContextVar(
    "current_run", default=None
)
_PROVIDER: Optional[TracerProvider] = None


class SpanStamper(SpanProcessor):
    """Stamps the current run's ids onto every span as it starts, and names
    the model a span used as it ends.

    Doing it here rather than at each call site is what covers the spans
    Strands creates on its own.
    """

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        ids = _CURRENT_RUN.get()
        if ids is None:
            return
        span.set_attribute(ATTR_RUN_ID, ids.run_id)
        span.set_attribute(ATTR_INCIDENT_ID, ids.incident_id)
        span.set_attribute(ATTR_SESSION_ID, ids.run_id)
        span.set_attribute(ATTR_AGENT_VERSION, ids.agent_version)
        if span.parent is None:
            span.set_attribute(OI_SPAN_KIND, "AGENT")
            span.set_attribute(OI_TAGS, [f"run.id={ids.run_id}", f"incident.id={ids.incident_id}"])
            span.set_attribute(
                OI_METADATA, json.dumps({"run_id": ids.run_id, "incident_id": ids.incident_id})
            )

    def on_end(self, span: Any) -> None:
        """Swap the gateway alias for the model it routes to, and count cached tokens once.

        Strands sets ``gen_ai.request.model`` after the span starts, to the
        alias (``claude``). Runs before the OpenInference processor, which
        copies it to ``llm.model_name``: Phoenix then shows
        ``claude-sonnet-5-5`` or ``gpt-4o``, prices it, and the vendor is per
        span. The alias stays as ``llm.gateway_alias``. Like that processor,
        this rewrites the ended span's ``_attributes``.

        The gateway speaks OpenAI's format, where the input count includes
        cached reads and writes. The processor follows Strands' Anthropic
        provider, where it doesn't, and adds them to it. Taking them out here
        leaves Phoenix the call's real prompt size, of which only the uncached
        part is priced at the input rate.
        """
        attrs = getattr(span, "_attributes", None)
        alias = attrs.get(GEN_AI_REQUEST_MODEL) if attrs else None
        target = gateway_models().get(alias) if isinstance(alias, str) else None
        if target is None:
            return
        rewritten = {**attrs, GEN_AI_REQUEST_MODEL: target.model, ATTR_GATEWAY_ALIAS: alias}
        if target.provider:
            rewritten[OI_LLM_PROVIDER] = target.provider
        cached = sum(int(attrs.get(key) or 0) for key in GEN_AI_CACHED_TOKENS)
        if cached:
            for key in GEN_AI_INPUT_TOKENS:
                if isinstance(attrs.get(key), int):
                    rewritten[key] = max(0, attrs[key] - cached)
        span._attributes = rewritten


def init_tracer_provider(service_name: str = "kafka-sre-agent") -> Optional[TracerProvider]:
    """Install the global tracer provider once. Opens no connection."""
    global _PROVIDER
    if _PROVIDER is not None or os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        return _PROVIDER

    project = os.environ.get("PHOENIX_PROJECT_NAME", "").strip() or service_name
    provider = TracerProvider(
        resource=Resource.create({"service.name": service_name, OI_PROJECT_NAME: project})
    )
    # Processors run in registration order: stamp (and name the model), then
    # translate, then export.
    provider.add_span_processor(SpanStamper())
    from openinference.instrumentation.strands_agents import (
        StrandsAgentsToOpenInferenceProcessor,
    )

    provider.add_span_processor(StrandsAgentsToOpenInferenceProcessor())

    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or (
        os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", DEFAULT_ENDPOINT).rstrip("/") + "/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))

    trace.set_tracer_provider(provider)
    _PROVIDER = provider
    return provider


@contextlib.contextmanager
def run_context(
    *, run_id: str, incident_id: str, agent_version: str, tracer: Any = None
) -> Iterator[Any]:
    """Open the run's root span; every span created inside carries its ids.

    The ids live in a ContextVar, so tasks created inside this block (the
    supervisor driver, sub-agent streams) inherit them.
    """
    token = _CURRENT_RUN.set(RunIds(run_id, incident_id, agent_version))
    try:
        with (tracer or trace.get_tracer("kafka-sre-agent")).start_as_current_span(
            "agent.run"
        ) as span:
            yield span
    finally:
        _CURRENT_RUN.reset(token)


def flush(timeout_millis: int = 5000) -> None:
    """Export pending spans now, so a finished run's trace shows up straight away.

    Blocks for up to ``timeout_millis`` when the collector is unreachable, so
    call it off the event loop.
    """
    if _PROVIDER is not None:
        with contextlib.suppress(Exception):
            _PROVIDER.force_flush(timeout_millis)
