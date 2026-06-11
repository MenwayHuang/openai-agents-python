"""Helpers for rendering tool errors in trace-safe form.

学习提示：工具错误可能包含敏感数据。这里根据 trace_include_sensitive_data 决定是否脱敏。
"""

REDACTED_TOOL_ERROR_MESSAGE = "Tool execution failed. Error details are redacted."


def get_trace_tool_error(*, trace_include_sensitive_data: bool, error_message: str) -> str:
    """Return a trace-safe tool error string based on the sensitive-data setting."""
    return error_message if trace_include_sensitive_data else REDACTED_TOOL_ERROR_MESSAGE
