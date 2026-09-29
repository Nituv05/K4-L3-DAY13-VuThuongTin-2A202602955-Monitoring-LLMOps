from __future__ import annotations

from contextlib import contextmanager

from app import agent as agent_module


class ManagedPrompt:
    version = 3

    def compile(self, **variables: str) -> str:
        return (
            f"Feature={variables['feature']}\n"
            f"Docs={variables['docs']}\n"
            f"Question={variables['message']}"
        )


class RecordingLangfuseClient:
    def __init__(self) -> None:
        self.prompt = ManagedPrompt()
        self.span_updates: list[dict] = []
        self.observation_calls: list[dict] = []
        self.observation_updates: list[dict] = []

    def get_prompt(self, name: str, **kwargs):
        return self.prompt

    def update_current_span(self, **kwargs) -> None:
        self.span_updates.append(kwargs)

    @contextmanager
    def start_as_current_observation(self, **kwargs):
        self.observation_calls.append(kwargs)
        observation = RecordingObservation(self.observation_updates)
        yield observation


class RecordingObservation:
    def __init__(self, updates: list[dict]) -> None:
        self.updates = updates

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


def test_agent_records_prompt_version_with_v4_observation_api(monkeypatch) -> None:
    monkeypatch.setenv("LANGFUSE_PROMPT_NAME", "day13-chat")
    monkeypatch.setenv("LANGFUSE_PROMPT_LABEL", "production")
    client = RecordingLangfuseClient()
    monkeypatch.setattr(agent_module, "get_langfuse_client", lambda: client)
    monkeypatch.setattr(agent_module, "tracing_enabled", lambda: True)

    propagated: list[dict] = []

    @contextmanager
    def record_attributes(**kwargs):
        propagated.append(kwargs)
        yield

    monkeypatch.setattr(agent_module, "propagate_attributes", record_attributes)

    agent = agent_module.LabAgent()
    agent_module.LabAgent.run.__wrapped__(
        agent,
        user_id="student-01",
        feature="qa",
        session_id="session-01",
        message="Explain traces",
        correlation_id="req-12345678",
    )

    span_update = client.span_updates[-1]
    assert span_update["metadata"] == {
        "doc_count": 1,
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
        "prompt_fetch_error": "",
    }
    assert span_update["version"] == "3"
    assert propagated[0]["metadata"]["correlation_id"] == "req-12345678"
    assert len(propagated) == 1

    retrieval, generation = client.observation_calls
    assert retrieval["as_type"] == "retriever"
    assert retrieval["name"] == "retrieval"
    assert retrieval["input"] == {"query_char_count": len("Explain traces")}
    assert generation["as_type"] == "generation"
    assert generation["model"] == agent.model
    assert generation["prompt"] is client.prompt
    assert generation["input"] == {
        "prompt_name": "day13-chat",
        "prompt_label": "production",
        "prompt_version": "3",
        "prompt_source": "langfuse",
    }
    assert "Feature=" not in str(generation["input"])

    retrieval_update, generation_update = client.observation_updates
    assert retrieval_update["output"]["document_count"] == 1
    assert generation_update["usage_details"]["input"] > 0
    assert generation_update["usage_details"]["output"] > 0
    assert set(generation_update["cost_details"]) == {"input", "output"}
    assert "Starter answer" not in str(generation_update)
