from __future__ import annotations

# 中文学习注释：
# 这个文件是 guardrail 的运行时执行器。
# guardrail.py 定义数据结构和装饰器；这里负责：
# - 创建 guardrail span；
# - 并发运行多个 guardrail；
# - tripwire 触发时取消其他 guardrail；
# - 流式模式下把 guardrail 结果写入队列。

import asyncio
from typing import Any

from ..agent import Agent
from ..exceptions import InputGuardrailTripwireTriggered, OutputGuardrailTripwireTriggered
from ..guardrail import (
    InputGuardrail,
    InputGuardrailResult,
    OutputGuardrail,
    OutputGuardrailResult,
)
from ..items import TResponseInputItem
from ..result import RunResultStreaming
from ..run_context import RunContextWrapper, TContext
from ..tracing import Span, SpanError, guardrail_span
from ..util import _error_tracing

__all__ = [
    "run_single_input_guardrail",
    "run_single_output_guardrail",
    "run_input_guardrails_with_queue",
    "run_input_guardrails",
    "run_output_guardrails",
    "input_guardrail_tripwire_triggered_for_stream",
]


async def run_single_input_guardrail(
    agent: Agent[Any],
    guardrail: InputGuardrail[TContext],
    input: str | list[TResponseInputItem],
    context: RunContextWrapper[TContext],
) -> InputGuardrailResult:
    # 单个 input guardrail 执行，并把 triggered 状态写入 trace span。
    with guardrail_span(guardrail.get_name()) as span_guardrail:
        result = await guardrail.run(agent, input, context)
        span_guardrail.span_data.triggered = result.output.tripwire_triggered
        return result


async def run_single_output_guardrail(
    guardrail: OutputGuardrail[TContext],
    agent: Agent[Any],
    agent_output: Any,
    context: RunContextWrapper[TContext],
) -> OutputGuardrailResult:
    # 单个 output guardrail 执行，检查最终输出。
    with guardrail_span(guardrail.get_name()) as span_guardrail:
        result = await guardrail.run(agent=agent, agent_output=agent_output, context=context)
        span_guardrail.span_data.triggered = result.output.tripwire_triggered
        return result


async def run_input_guardrails_with_queue(
    agent: Agent[Any],
    guardrails: list[InputGuardrail[TContext]],
    input: str | list[TResponseInputItem],
    context: RunContextWrapper[TContext],
    streamed_result: RunResultStreaming,
    parent_span: Span[Any] | None,
) -> None:
    """Run guardrails concurrently and stream results into the queue."""
    # 流式模式专用：guardrail 和模型流可能并发。
    # 每个 guardrail 完成后放入 queue；如果 tripwire 触发，取消剩余 guardrail。
    queue = streamed_result._input_guardrail_queue

    guardrail_tasks = [
        # create_task 启动并发 guardrail。
        asyncio.create_task(run_single_input_guardrail(agent, guardrail, input, context))
        for guardrail in guardrails
    ]
    guardrail_results = []
    try:
        for done in asyncio.as_completed(guardrail_tasks):
            # as_completed 谁先完成就先处理谁，有利于快速响应 tripwire。
            result = await done
            guardrail_results.append(result)
            if result.output.tripwire_triggered:
                # 一旦任意 guardrail 触发，记录结果并取消其他未完成检查。
                streamed_result.input_guardrail_results = (
                    streamed_result.input_guardrail_results + guardrail_results
                )
                guardrail_results = []
                streamed_result._triggered_input_guardrail_result = result
                queue.put_nowait(result)
                for t in guardrail_tasks:
                    t.cancel()
                await asyncio.gather(*guardrail_tasks, return_exceptions=True)
                span_error = SpanError(
                    message="Guardrail tripwire triggered",
                    data={
                        "guardrail": result.guardrail.get_name(),
                        "type": "input_guardrail",
                    },
                )
                if parent_span is not None:
                    _error_tracing.attach_error_to_span(parent_span, span_error)
                else:
                    # Early first-turn streamed guardrails can run before the agent span exists.
                    _error_tracing.attach_error_to_current_span(span_error)
                break
            queue.put_nowait(result)
    except BaseException:
        for t in guardrail_tasks:
            if not t.done():
                t.cancel()
        await asyncio.gather(*guardrail_tasks, return_exceptions=True)
        raise

    streamed_result.input_guardrail_results = (
        streamed_result.input_guardrail_results + guardrail_results
    )


async def run_input_guardrails(
    agent: Agent[Any],
    guardrails: list[InputGuardrail[TContext]],
    input: str | list[TResponseInputItem],
    context: RunContextWrapper[TContext],
) -> list[InputGuardrailResult]:
    """Run input guardrails concurrently and raise on tripwires."""
    # 非流式路径：并发执行所有 input guardrail，任何一个触发就抛 InputGuardrailTripwireTriggered。
    if not guardrails:
        return []

    guardrail_tasks = [
        asyncio.create_task(run_single_input_guardrail(agent, guardrail, input, context))
        for guardrail in guardrails
    ]

    guardrail_results: list[InputGuardrailResult] = []

    for done in asyncio.as_completed(guardrail_tasks):
        # guardrail 顺序不保证和列表一致，按完成先后处理。
        result = await done
        if result.output.tripwire_triggered:
            for t in guardrail_tasks:
                t.cancel()
            await asyncio.gather(*guardrail_tasks, return_exceptions=True)
            _error_tracing.attach_error_to_current_span(
                SpanError(
                    message="Guardrail tripwire triggered",
                    data={"guardrail": result.guardrail.get_name()},
                )
            )
            raise InputGuardrailTripwireTriggered(result)
        guardrail_results.append(result)

    return guardrail_results


async def run_output_guardrails(
    guardrails: list[OutputGuardrail[TContext]],
    agent: Agent[TContext],
    agent_output: Any,
    context: RunContextWrapper[TContext],
) -> list[OutputGuardrailResult]:
    """Run output guardrails in parallel and raise on tripwires."""
    # 输出 guardrail 只在最终输出产生后运行。
    # 任意 tripwire 都会抛 OutputGuardrailTripwireTriggered。
    if not guardrails:
        return []

    guardrail_tasks = [
        asyncio.create_task(run_single_output_guardrail(guardrail, agent, agent_output, context))
        for guardrail in guardrails
    ]

    guardrail_results: list[OutputGuardrailResult] = []

    for done in asyncio.as_completed(guardrail_tasks):
        result = await done
        if result.output.tripwire_triggered:
            for t in guardrail_tasks:
                t.cancel()
            await asyncio.gather(*guardrail_tasks, return_exceptions=True)
            _error_tracing.attach_error_to_current_span(
                SpanError(
                    message="Guardrail tripwire triggered",
                    data={"guardrail": result.guardrail.get_name()},
                )
            )
            raise OutputGuardrailTripwireTriggered(result)
        guardrail_results.append(result)

    return guardrail_results


async def input_guardrail_tripwire_triggered_for_stream(
    streamed_result: RunResultStreaming,
) -> bool:
    """Return True if any input guardrail triggered during a streamed run."""
    # 流式收尾/持久化前检查后台 guardrail task 是否触发过。
    task = streamed_result._input_guardrails_task
    if task is None:
        return False

    if not task.done():
        await task

    return any(
        guardrail_result.output.tripwire_triggered
        for guardrail_result in streamed_result.input_guardrail_results
    )
