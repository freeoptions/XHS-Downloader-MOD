"""GUI 整队列重试上下文；不改共享下载器配置。"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DeferredRetryState:
    retrying: bool = False
    download_failed: bool = False
    retryable: bool = False
    http1_urls: set[str] = field(default_factory=set)
    png_failures: set[str] = field(default_factory=set)
    partial_outcomes: dict[tuple[Path, str], bool] = field(default_factory=dict)


DEFERRED_RETRY: ContextVar[DeferredRetryState | None] = ContextVar(
    "deferred_retry", default=None,
)


@contextmanager
def defer_retries(state: DeferredRetryState):
    token = DEFERRED_RETRY.set(state)
    try:
        yield
    finally:
        DEFERRED_RETRY.reset(token)
