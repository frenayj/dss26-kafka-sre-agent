"""Every span inside a run carries the run's ids, Strands' own spans included.

Runs against real finished spans (OTel's in-memory exporter), so the tests
assert what Phoenix would actually receive.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from agent import tracing
from agent.models import GatewayModel, gateway_models
from harness.seed import seed_phoenix_costs


@pytest.fixture
def traced(monkeypatch):
    monkeypatch.delenv("OTEL_SDK_DISABLED")  # set suite-wide by conftest
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(tracing.SpanStamper())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield exporter, provider.get_tracer("test")


def _run(tracer):
    return tracing.run_context(run_id="r1", incident_id="PI7K3FQ", agent_version="0.1.0", tracer=tracer)


def _spans(exporter):
    return {s.name: dict(s.attributes) for s in exporter.get_finished_spans()}


def test_ids_are_stamped_on_every_span(traced):
    exporter, tracer = traced
    with _run(tracer):
        with tracer.start_as_current_span("model call"):
            with tracer.start_as_current_span("tool call"):
                pass
    spans = _spans(exporter)
    assert set(spans) == {"agent.run", "model call", "tool call"}
    for name, attrs in spans.items():
        assert attrs[tracing.ATTR_RUN_ID] == "r1", name
        assert attrs[tracing.ATTR_INCIDENT_ID] == "PI7K3FQ", name
        assert attrs[tracing.ATTR_SESSION_ID] == "r1", name


def test_root_span_is_an_agent_with_filterable_tags(traced):
    exporter, tracer = traced
    with _run(tracer):
        pass
    root = _spans(exporter)["agent.run"]
    assert root[tracing.OI_SPAN_KIND] == "AGENT"
    assert list(root[tracing.OI_TAGS]) == ["run.id=r1", "incident.id=PI7K3FQ"]
    assert json.loads(root[tracing.OI_METADATA]) == {"run_id": "r1", "incident_id": "PI7K3FQ"}


def test_ids_do_not_leak_outside_the_run(traced):
    exporter, tracer = traced
    with _run(tracer):
        pass
    with tracer.start_as_current_span("after"):
        pass
    assert tracing.ATTR_RUN_ID not in _spans(exporter)["after"]


def test_ids_reach_tasks_created_inside_the_run(traced):
    """The server drives the supervisor in an asyncio Task created in the run."""
    exporter, tracer = traced

    async def work():
        with tracer.start_as_current_span("in task"):
            await asyncio.sleep(0)

    async def main():
        with _run(tracer):
            await asyncio.create_task(work())

    asyncio.run(main())
    assert _spans(exporter)["in task"][tracing.ATTR_RUN_ID] == "r1"


def _chat(tracer, model):
    with tracer.start_as_current_span("chat") as span:
        # Strands sets the model after the span starts.
        span.set_attribute(tracing.GEN_AI_REQUEST_MODEL, model)


def test_spans_name_the_model_behind_the_gateway_alias(traced, monkeypatch):
    monkeypatch.setattr(
        tracing, "gateway_models", lambda: {"claude": GatewayModel("anthropic", "claude-sonnet-5-5")}
    )
    exporter, tracer = traced
    with _run(tracer):
        _chat(tracer, "claude")
    spans = _spans(exporter)
    chat = spans["chat"]
    assert chat[tracing.GEN_AI_REQUEST_MODEL] == "claude-sonnet-5-5"
    assert chat[tracing.OI_LLM_PROVIDER] == "anthropic"
    assert chat[tracing.ATTR_GATEWAY_ALIAS] == "claude"
    assert chat[tracing.ATTR_RUN_ID] == "r1"
    assert tracing.OI_LLM_PROVIDER not in spans["agent.run"]  # no model, no vendor


def test_a_model_the_gateway_does_not_know_is_left_as_is(traced, monkeypatch):
    monkeypatch.setattr(tracing, "gateway_models", lambda: {})
    exporter, tracer = traced
    with _run(tracer):
        _chat(tracer, "some-model")
    chat = _spans(exporter)["chat"]
    assert chat[tracing.GEN_AI_REQUEST_MODEL] == "some-model"
    assert tracing.OI_LLM_PROVIDER not in chat


def test_cached_tokens_reach_phoenix_once(traced, monkeypatch):
    """The gateway's input count includes cached tokens; the processor adds them again."""
    from openinference.instrumentation.strands_agents.processor import (
        StrandsAgentsToOpenInferenceProcessor,
    )

    monkeypatch.setattr(
        tracing, "gateway_models", lambda: {"claude": GatewayModel("anthropic", "claude-sonnet-5-5")}
    )
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(tracing.SpanStamper())
    provider.add_span_processor(StrandsAgentsToOpenInferenceProcessor())
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("test").start_as_current_span("chat") as span:
        span.set_attribute("gen_ai.system", "strands-agents")  # what the processor maps
        span.set_attribute(tracing.GEN_AI_REQUEST_MODEL, "claude")
        # One call as the gateway reports it: a 12,000-token prompt, 9,000 of
        # it read from the cache and 2,000 written to it.
        span.set_attribute("gen_ai.usage.input_tokens", 12_000)
        span.set_attribute("gen_ai.usage.prompt_tokens", 12_000)
        span.set_attribute("gen_ai.usage.cache_read_input_tokens", 9_000)
        span.set_attribute("gen_ai.usage.cache_write_input_tokens", 2_000)
        span.set_attribute("gen_ai.usage.output_tokens", 100)
    chat = _spans(exporter)["chat"]
    assert chat["llm.token_count.prompt"] == 12_000
    assert chat["llm.token_count.prompt_details.cache_read"] == 9_000
    assert chat["llm.token_count.prompt_details.cache_write"] == 2_000


def test_a_call_without_cache_keeps_its_input_count(traced, monkeypatch):
    monkeypatch.setattr(
        tracing, "gateway_models", lambda: {"claude": GatewayModel("anthropic", "claude-sonnet-5-5")}
    )
    exporter, tracer = traced
    with tracer.start_as_current_span("chat") as span:
        span.set_attribute(tracing.GEN_AI_REQUEST_MODEL, "claude")
        span.set_attribute("gen_ai.usage.input_tokens", 4_862)
    assert _spans(exporter)["chat"]["gen_ai.usage.input_tokens"] == 4_862


def test_every_gateway_model_has_a_phoenix_price():
    models = gateway_models()
    assert models["claude"].provider == "anthropic"
    priced = seed_phoenix_costs.BUILT_IN | {m["name"] for m in seed_phoenix_costs.MODELS}
    assert {m.model for m in models.values()} <= priced


def test_tracing_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
    monkeypatch.setattr(tracing, "_PROVIDER", None)
    assert tracing.init_tracer_provider() is None


def test_fastapi_leaves_the_tracer_provider_to_us(monkeypatch):
    """With an OTLP endpoint set, FastAPI's startup would install its own
    provider before the lifespan installs ours (see agent/server.py)."""
    from fastapi.telemetry._runtime import _configure_from_environment
    from opentelemetry import trace

    from agent import server

    monkeypatch.delenv("OTEL_SDK_DISABLED")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://phoenix:6006")
    before = trace.get_tracer_provider()
    _configure_from_environment(server.app._telemetry)
    assert trace.get_tracer_provider() is before
