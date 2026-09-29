from __future__ import annotations

import os
from contextlib import contextmanager, nullcontext
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


def get_langfuse_client():
    return get_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


class _NoopObservation:
    def update(self, **kwargs: Any) -> None:
        return None


def observation_scope(client: Any, *, enabled: bool, **kwargs: Any):
    """Create an SDK v4 observation when tracing is configured, else a no-op."""
    if not enabled:
        return nullcontext(_NoopObservation())
    return client.start_as_current_observation(**kwargs)
