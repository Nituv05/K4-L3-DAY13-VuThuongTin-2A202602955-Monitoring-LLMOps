from __future__ import annotations

import os
import time
from contextlib import nullcontext
from dataclasses import dataclass

from . import metrics
from .mock_llm import FakeLLM
from .mock_rag import retrieve
from .pii import hash_user_id
from .prompt_management import resolve_prompt
from .tracing import (
    get_langfuse_client,
    observation_scope,
    observe,
    propagate_attributes,
    tracing_enabled,
)


@dataclass
class AgentResult:
    answer: str
    latency_ms: int
    ttft_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float
    quality_score: float


class LabAgent:
    def __init__(self, model: str = "claude-sonnet-4-5") -> None:
        self.model = model
        self.llm = FakeLLM(model=model)

    @observe(name="lab-agent-run", as_type="agent", capture_input=False, capture_output=False)
    def run(
        self,
        user_id: str,
        feature: str,
        session_id: str,
        message: str,
        correlation_id: str,
    ) -> AgentResult:
        langfuse_client = get_langfuse_client()
        enabled = tracing_enabled()
        trace_attributes = {
            "user_id": hash_user_id(user_id),
            "session_id": session_id,
            "tags": ["lab", feature, self.model],
            "trace_name": "day13-agent-request",
            "environment": os.getenv("APP_ENV", "dev"),
            "metadata": {
                "feature": feature,
                "model": self.model,
                "correlation_id": correlation_id,
            },
        }
        with propagate_attributes(**trace_attributes) if enabled else nullcontext():
            started = time.perf_counter()
            with observation_scope(
                langfuse_client,
                enabled=enabled,
                as_type="retriever",
                name="retrieval",
                input={"query_char_count": len(message)},
                metadata={"feature": feature},
            ) as retrieval_observation:
                retrieval_started = time.perf_counter()
                docs = retrieve(message)
                retrieval_observation.update(
                    output={"document_count": len(docs)},
                    metadata={
                        "duration_ms": round(
                            (time.perf_counter() - retrieval_started) * 1000, 2
                        )
                    },
                )
            prompt = resolve_prompt(
                langfuse_client,
                feature=feature,
                docs=docs,
                message=message,
                enabled=enabled,
            )
            if enabled:
                langfuse_client.update_current_span(
                    metadata={
                        "doc_count": len(docs),
                        "prompt_name": prompt.name,
                        "prompt_label": prompt.label,
                        "prompt_version": prompt.version,
                        "prompt_source": prompt.source,
                        "prompt_fetch_error": prompt.fetch_error or "",
                    },
                    version=prompt.version,
                )
            with observation_scope(
                langfuse_client,
                enabled=enabled,
                as_type="generation",
                name="llm-generation",
                model=self.model,
                prompt=prompt.managed_prompt,
                input={
                    "prompt_name": prompt.name,
                    "prompt_label": prompt.label,
                    "prompt_version": prompt.version,
                    "prompt_source": prompt.source,
                },
                metadata={"feature": feature},
            ) as generation_observation:
                response = self.llm.generate(prompt.text)
                input_cost_usd, output_cost_usd = self._estimate_cost_components(
                    response.usage.input_tokens, response.usage.output_tokens
                )
                generation_observation.update(
                    # Do not send prompt or completion content: only safe metadata.
                    output={"output_char_count": len(response.text)},
                    usage_details={
                        "input": response.usage.input_tokens,
                        "output": response.usage.output_tokens,
                    },
                    cost_details={
                        "input": input_cost_usd,
                        "output": output_cost_usd,
                    },
                    metadata={"ttft_ms": response.ttft_ms},
                )
            quality_score = self._heuristic_quality(message, response.text, docs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            cost_usd = round(input_cost_usd + output_cost_usd, 6)

        metrics.record_request(
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            cost_usd=cost_usd,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            quality_score=quality_score,
        )

        return AgentResult(
            answer=response.text,
            latency_ms=latency_ms,
            ttft_ms=response.ttft_ms,
            tokens_in=response.usage.input_tokens,
            tokens_out=response.usage.output_tokens,
            cost_usd=cost_usd,
            quality_score=quality_score,
        )

    def _estimate_cost(self, tokens_in: int, tokens_out: int) -> float:
        input_cost, output_cost = self._estimate_cost_components(tokens_in, tokens_out)
        return round(input_cost + output_cost, 6)

    def _estimate_cost_components(
        self, tokens_in: int, tokens_out: int
    ) -> tuple[float, float]:
        input_cost = (tokens_in / 1_000_000) * 3
        output_cost = (tokens_out / 1_000_000) * 15
        return round(input_cost, 6), round(output_cost, 6)

    def _heuristic_quality(self, question: str, answer: str, docs: list[str]) -> float:
        score = 0.5
        if docs:
            score += 0.2
        if len(answer) > 40:
            score += 0.1
        if question.lower().split()[0:1] and any(token in answer.lower() for token in question.lower().split()[:3]):
            score += 0.1
        if "[REDACTED" in answer:
            score -= 0.2
        return round(max(0.0, min(1.0, score)), 2)
