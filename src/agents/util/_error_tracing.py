from typing import Any

from ..logger import logger
from ..tracing import Span, SpanError, get_current_span

# 学习提示：这些 helper 把错误挂到当前 trace span 上，便于调试时看到错误发生在哪一步。


def attach_error_to_span(span: Span[Any], error: SpanError) -> None:
    span.set_error(error)


def attach_error_to_current_span(error: SpanError) -> None:
    span = get_current_span()
    if span:
        attach_error_to_span(span, error)
    else:
        logger.warning(f"No span to add error {error} to")
