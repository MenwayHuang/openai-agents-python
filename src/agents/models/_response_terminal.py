from __future__ import annotations

from typing import Any

from openai.types.responses import Response

from ..exceptions import ModelBehaviorError, _mark_error_to_drain_stream_events

# 学习提示：Responses API 流式调用不一定只以“正常完成”收尾，
# 也可能收到失败、取消、不完整等 terminal event。这个文件把这些终止事件
# 格式化成 SDK 内部的 ModelBehaviorError，方便上层统一处理。


def format_response_terminal_failure(
    event_type: str,
    response: Response | None,
) -> str:
    # 把 response.status / error / incomplete_details 拼成易排查的错误信息。
    message = f"Responses stream ended with terminal event `{event_type}`."
    if response is None:
        return message

    details: list[str] = []
    status = getattr(response, "status", None)
    if status:
        details.append(f"status={status}")
    error = getattr(response, "error", None)
    if error:
        details.append(f"error={error}")
    incomplete_details = getattr(response, "incomplete_details", None)
    if incomplete_details:
        details.append(f"incomplete_details={incomplete_details}")

    if details:
        message = f"{message} {'; '.join(details)}."
    return message


def format_response_error_event(event_type: str, event: Any) -> str:
    # error event 自身可能带 code/message/param；这里保留关键字段即可。
    message = f"Responses stream ended with terminal event `{event_type}`."
    details: list[str] = []
    code = getattr(event, "code", None)
    if code:
        details.append(f"code={code}")
    error_message = getattr(event, "message", None)
    if error_message:
        details.append(f"message={error_message}")
    param = getattr(event, "param", None)
    if param:
        details.append(f"param={param}")

    if details:
        message = f"{message} {'; '.join(details)}."
    return message


def response_terminal_failure_error(
    event_type: str,
    response: Response | None,
) -> ModelBehaviorError:
    error = ModelBehaviorError(format_response_terminal_failure(event_type, response))
    # 标记“需要继续 drain 流事件”：即使已判错，也尽量读完剩余事件，避免连接状态混乱。
    _mark_error_to_drain_stream_events(error)
    return error


def response_error_event_failure_error(event_type: str, event: Any) -> ModelBehaviorError:
    error = ModelBehaviorError(format_response_error_event(event_type, event))
    # 这里同样要求 drain，属于流式协议稳定性处理，不是业务逻辑。
    _mark_error_to_drain_stream_events(error)
    return error
