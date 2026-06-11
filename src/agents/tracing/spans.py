"""Span 生命周期实现。

中文学习说明：
- `SpanData` 只定义数据，`SpanImpl` 才负责 start/finish/error/export。
- `contextvars` 用来在异步任务中保存“当前 span”，避免多并发请求之间串上下文。
- `NoOpSpan` 让 tracing 关闭时调用代码不需要到处写 if。
"""

from __future__ import annotations

import abc
import contextvars
from typing import Any, Generic, TypeVar

from typing_extensions import TypedDict

from ..logger import logger
from . import util
from .processor_interface import TracingProcessor
from .scope import Scope
from .span_data import SpanData

TSpanData = TypeVar("TSpanData", bound=SpanData)
_SPAN_METADATA_ROUTING_KEYS = ("agent_harness_id",)


class SpanError(TypedDict):
    """Represents an error that occurred during span execution.

    Attributes:
        message: A human-readable error description
        data: Optional dictionary containing additional error context
    """

    message: str
    data: dict[str, Any] | None


class Span(abc.ABC, Generic[TSpanData]):
    """Base class for representing traceable operations with timing and context.

    A span represents a single operation within a trace (e.g., an LLM call, tool execution,
    or agent run). Spans track timing, relationships between operations, and operation-specific
    data.

    Type Args:
        TSpanData: The type of span-specific data this span contains.

    Example:
        ```python
        # Creating a custom span
        with custom_span("database_query", {
            "operation": "SELECT",
            "table": "users"
        }) as span:
            results = await db.query("SELECT * FROM users")
            span.set_output({"count": len(results)})

        # Handling errors in spans
        with custom_span("risky_operation") as span:
            try:
                result = perform_risky_operation()
            except Exception as e:
                span.set_error({
                    "message": str(e),
                    "data": {"operation": "risky_operation"}
                })
                raise
        ```

        Notes:
        - Spans automatically nest under the current trace
        - Use context managers for reliable start/finish
        - Include relevant data but avoid sensitive information
        - Handle errors properly using set_error()
    """
    # Span 是 trace 里的一个时间片段。Generic[TSpanData] 表示这个 span 携带哪种数据结构。

    @property
    @abc.abstractmethod
    def trace_id(self) -> str:
        """The ID of the trace this span belongs to.

        Returns:
            str: Unique identifier of the parent trace.
        """
        pass

    @property
    @abc.abstractmethod
    def span_id(self) -> str:
        """Unique identifier for this span.

        Returns:
            str: The span's unique ID within its trace.
        """
        pass

    @property
    @abc.abstractmethod
    def span_data(self) -> TSpanData:
        """Operation-specific data for this span.

        Returns:
            TSpanData: Data specific to this type of span (e.g., LLM generation data).
        """
        pass

    @abc.abstractmethod
    def start(self, mark_as_current: bool = False):
        """
        Start the span.

        Args:
            mark_as_current: If true, the span will be marked as the current span.
        """
        pass

    @abc.abstractmethod
    def finish(self, reset_current: bool = False) -> None:
        """
        Finish the span.

        Args:
            reset_current: If true, the span will be reset as the current span.
        """
        pass

    @abc.abstractmethod
    def __enter__(self) -> Span[TSpanData]:
        pass

    @abc.abstractmethod
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    @property
    @abc.abstractmethod
    def parent_id(self) -> str | None:
        """ID of the parent span, if any.

        Returns:
            str | None: The parent span's ID, or None if this is a root span.
        """
        pass

    @abc.abstractmethod
    def set_error(self, error: SpanError) -> None:
        pass

    @property
    @abc.abstractmethod
    def error(self) -> SpanError | None:
        """Any error that occurred during span execution.

        Returns:
            SpanError | None: Error details if an error occurred, None otherwise.
        """
        pass

    @abc.abstractmethod
    def export(self) -> dict[str, Any] | None:
        pass

    @property
    @abc.abstractmethod
    def started_at(self) -> str | None:
        """When the span started execution.

        Returns:
            str | None: ISO format timestamp of span start, None if not started.
        """
        pass

    @property
    @abc.abstractmethod
    def ended_at(self) -> str | None:
        """When the span finished execution.

        Returns:
            str | None: ISO format timestamp of span end, None if not finished.
        """
        pass

    @property
    @abc.abstractmethod
    def tracing_api_key(self) -> str | None:
        """The API key to use when exporting this span."""
        pass

    @property
    def trace_metadata(self) -> dict[str, Any] | None:
        """Trace-level metadata inherited by this span, if available."""
        return None


class NoOpSpan(Span[TSpanData]):
    """A no-op implementation of Span that doesn't record any data.

    Used when tracing is disabled but span operations still need to work.

    Args:
        span_data: The operation-specific data for this span.
    """
    # tracing disabled 时返回 NoOpSpan：代码照样可以 with/start/finish，
    # 但不会记录或导出任何数据。

    __slots__ = ("_span_data", "_prev_span_token")

    def __init__(self, span_data: TSpanData):
        self._span_data = span_data
        self._prev_span_token: contextvars.Token[Span[TSpanData] | None] | None = None

    @property
    def trace_id(self) -> str:
        return "no-op"

    @property
    def span_id(self) -> str:
        return "no-op"

    @property
    def span_data(self) -> TSpanData:
        return self._span_data

    @property
    def parent_id(self) -> str | None:
        return None

    def start(self, mark_as_current: bool = False):
        # 即使不记录数据，也要正确维护当前上下文，避免下游代码拿 current_span 出错。
        if mark_as_current:
            self._prev_span_token = Scope.set_current_span(self)

    def finish(self, reset_current: bool = False) -> None:
        if reset_current and self._prev_span_token is not None:
            Scope.reset_current_span(self._prev_span_token)
            self._prev_span_token = None

    def __enter__(self) -> Span[TSpanData]:
        self.start(mark_as_current=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        reset_current = True
        if exc_type is GeneratorExit:
            logger.debug("GeneratorExit, skipping span reset")
            reset_current = False

        self.finish(reset_current=reset_current)

    def set_error(self, error: SpanError) -> None:
        pass

    @property
    def error(self) -> SpanError | None:
        return None

    def export(self) -> dict[str, Any] | None:
        return None

    @property
    def started_at(self) -> str | None:
        return None

    @property
    def ended_at(self) -> str | None:
        return None

    @property
    def tracing_api_key(self) -> str | None:
        return None


class SpanImpl(Span[TSpanData]):
    # 真正会记录的 Span 实现。processor 负责把 start/end 事件送给后端或本地缓冲。
    __slots__ = (
        "_trace_id",
        "_span_id",
        "_parent_id",
        "_started_at",
        "_ended_at",
        "_error",
        "_prev_span_token",
        "_processor",
        "_span_data",
        "_tracing_api_key",
        "_trace_metadata",
    )

    def __init__(
        self,
        trace_id: str,
        span_id: str | None,
        parent_id: str | None,
        processor: TracingProcessor,
        span_data: TSpanData,
        tracing_api_key: str | None,
        trace_metadata: dict[str, Any] | None = None,
    ):
        self._trace_id = trace_id
        self._span_id = span_id or util.gen_span_id()
        self._parent_id = parent_id
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._processor = processor
        self._error: SpanError | None = None
        self._prev_span_token: contextvars.Token[Span[TSpanData] | None] | None = None
        self._span_data = span_data
        self._tracing_api_key = tracing_api_key
        self._trace_metadata = trace_metadata

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @property
    def span_id(self) -> str:
        return self._span_id

    @property
    def span_data(self) -> TSpanData:
        return self._span_data

    @property
    def parent_id(self) -> str | None:
        return self._parent_id

    def start(self, mark_as_current: bool = False):
        # start 时打开始时间，并通知 TracingProcessor。
        if self.started_at is not None:
            logger.warning("Span already started")
            return

        self._started_at = util.time_iso()
        self._processor.on_span_start(self)
        if mark_as_current:
            # Scope 基于 contextvars 保存当前 span，支持 async 并发隔离。
            self._prev_span_token = Scope.set_current_span(self)

    def finish(self, reset_current: bool = False) -> None:
        # finish 时打结束时间，并通知 processor。reset_current 会恢复进入 span 前的上下文。
        if self.ended_at is not None:
            logger.warning("Span already finished")
            return

        self._ended_at = util.time_iso()
        self._processor.on_span_end(self)
        if reset_current and self._prev_span_token is not None:
            Scope.reset_current_span(self._prev_span_token)
            self._prev_span_token = None

    def __enter__(self) -> Span[TSpanData]:
        # context manager 用法：`with span:` 自动 start/finish。
        self.start(mark_as_current=True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        reset_current = True
        if exc_type is GeneratorExit:
            logger.debug("GeneratorExit, skipping span reset")
            reset_current = False

        self.finish(reset_current=reset_current)

    def set_error(self, error: SpanError) -> None:
        # 异常不会自动塞进 span，调用方需要在 except 里 set_error。
        self._error = error

    @property
    def error(self) -> SpanError | None:
        return self._error

    @property
    def started_at(self) -> str | None:
        return self._started_at

    @property
    def ended_at(self) -> str | None:
        return self._ended_at

    @property
    def tracing_api_key(self) -> str | None:
        return self._tracing_api_key

    @property
    def trace_metadata(self) -> dict[str, Any] | None:
        return self._trace_metadata

    def export(self) -> dict[str, Any] | None:
        # 导出成统一 payload，processor 可以上报到 OpenAI tracing 或其他观测系统。
        payload = {
            "object": "trace.span",
            "id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self._parent_id,
            "started_at": self._started_at,
            "ended_at": self._ended_at,
            "span_data": self.span_data.export(),
            "error": self._error,
        }
        metadata: dict[str, Any] = {}
        if self._trace_metadata is not None:
            metadata.update(
                {
                    key: self._trace_metadata[key]
                    for key in _SPAN_METADATA_ROUTING_KEYS
                    if key in self._trace_metadata
                }
            )
        span_data_metadata = getattr(self.span_data, "metadata", None)
        if isinstance(span_data_metadata, dict):
            metadata.update(
                {key: value for key, value in span_data_metadata.items() if key not in metadata}
            )
        if metadata:
            payload["metadata"] = metadata
        return payload
