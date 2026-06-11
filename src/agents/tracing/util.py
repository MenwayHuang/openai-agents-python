from .setup import get_trace_provider

# 学习提示：这些是 trace id/span id/group id 的便捷函数，实际生成逻辑委托给全局 provider。


def time_iso() -> str:
    """Return the current time in ISO 8601 format."""
    return get_trace_provider().time_iso()


def gen_trace_id() -> str:
    """Generate a new trace ID."""
    return get_trace_provider().gen_trace_id()


def gen_span_id() -> str:
    """Generate a new span ID."""
    return get_trace_provider().gen_span_id()


def gen_group_id() -> str:
    """Generate a new group ID."""
    return get_trace_provider().gen_group_id()
