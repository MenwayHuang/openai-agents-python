# 中文学习注释：
# 这个文件负责 Agent 的“结构化最终输出”。
# 当 Agent.output_type 不是 str/None 时，SDK 会把它转成 JSON Schema 发给模型，
# 再把模型返回的 JSON 字符串用 Pydantic TypeAdapter 校验成 Python 对象。
# 它和 function_schema.py 很像：一个处理工具参数 schema，一个处理最终输出 schema。

import abc
from dataclasses import dataclass
from typing import Any, get_args, get_origin

from pydantic import BaseModel, TypeAdapter
from typing_extensions import TypedDict

from .exceptions import ModelBehaviorError, UserError
from .strict_schema import ensure_strict_json_schema
from .tracing import SpanError
from .util import _error_tracing, _json

_WRAPPER_DICT_KEY = "response"


class AgentOutputSchemaBase(abc.ABC):
    """An object that captures the JSON schema of the output, as well as validating/parsing JSON
    produced by the LLM into the output type.
    """
    # abc.ABC + @abstractmethod 表示抽象基类。
    # 子类必须实现这些方法，才能作为可用的 output schema。

    @abc.abstractmethod
    def is_plain_text(self) -> bool:
        """Whether the output type is plain text (versus a JSON object)."""
        pass

    @abc.abstractmethod
    def name(self) -> str:
        """The name of the output type."""
        pass

    @abc.abstractmethod
    def json_schema(self) -> dict[str, Any]:
        """Returns the JSON schema of the output. Will only be called if the output type is not
        plain text.
        """
        pass

    @abc.abstractmethod
    def is_strict_json_schema(self) -> bool:
        """Whether the JSON schema is in strict mode. Strict mode constrains the JSON schema
        features, but guarantees valid JSON. See here for details:
        https://platform.openai.com/docs/guides/structured-outputs#supported-schemas
        """
        pass

    @abc.abstractmethod
    def validate_json(self, json_str: str) -> Any:
        """Validate a JSON string against the output type. You must return the validated object,
        or raise a `ModelBehaviorError` if the JSON is invalid.
        """
        pass


@dataclass(init=False)
class AgentOutputSchema(AgentOutputSchemaBase):
    """An object that captures the JSON schema of the output, as well as validating/parsing JSON
    produced by the LLM into the output type.
    """
    # init=False 表示 dataclass 不自动生成 __init__，因为下面需要手写初始化逻辑。
    # 这个类把任意 Python 类型包装成统一的 output schema/validator。

    output_type: type[Any]
    """The type of the output."""

    _type_adapter: TypeAdapter[Any]
    """A type adapter that wraps the output type, so that we can validate JSON."""

    _is_wrapped: bool
    """Whether the output type is wrapped in a dictionary. This is generally done if the base
    output type cannot be represented as a JSON Schema object.
    """

    _output_schema: dict[str, Any]
    """The JSON schema of the output."""

    _strict_json_schema: bool
    """Whether the JSON schema is in strict mode. We **strongly** recommend setting this to True,
    as it increases the likelihood of correct JSON input.
    """

    def __init__(self, output_type: type[Any], strict_json_schema: bool = True):
        """
        Args:
            output_type: The type of the output.
            strict_json_schema: Whether the JSON schema is in strict mode. We **strongly** recommend
                setting this to True, as it increases the likelihood of correct JSON input.
        """
        self.output_type = output_type
        self._strict_json_schema = strict_json_schema

        if output_type is None or output_type is str:
            # 普通文本输出不需要 JSON Schema。
            self._is_wrapped = False
            self._type_adapter = TypeAdapter(output_type)
            self._output_schema = self._type_adapter.json_schema()
            return

        # We should wrap for things that are not plain text, and for things that would definitely
        # not be a JSON Schema object.
        # JSON Schema 的顶层通常要求 object。
        # 如果 output_type 是 list[int] 这类非 object 类型，就包装成 {"response": ...}。
        self._is_wrapped = not _is_subclass_of_base_model_or_dict(output_type)

        if self._is_wrapped:
            # TypedDict 动态创建一个只包含 response 字段的 dict 类型。
            # 这样 list/int 等类型也能作为结构化输出返回。
            OutputType = TypedDict(
                "OutputType",
                {
                    _WRAPPER_DICT_KEY: output_type,  # type: ignore
                },
            )
            self._type_adapter = TypeAdapter(OutputType)
            self._output_schema = self._type_adapter.json_schema()
        else:
            self._type_adapter = TypeAdapter(output_type)
            self._output_schema = self._type_adapter.json_schema()

        if self._strict_json_schema:
            try:
                # strict schema 会收紧模型输出格式，提升可校验概率。
                self._output_schema = ensure_strict_json_schema(self._output_schema)
            except UserError as e:
                raise UserError(
                    "Strict JSON schema is enabled, but the output type is not valid. "
                    "Either make the output type strict, "
                    "or wrap your type with AgentOutputSchema(YourType, strict_json_schema=False)"
                ) from e

    def is_plain_text(self) -> bool:
        """Whether the output type is plain text (versus a JSON object)."""
        return self.output_type is None or self.output_type is str

    def is_strict_json_schema(self) -> bool:
        """Whether the JSON schema is in strict mode."""
        return self._strict_json_schema

    def json_schema(self) -> dict[str, Any]:
        """The JSON schema of the output type."""
        if self.is_plain_text():
            raise UserError("Output type is plain text, so no JSON schema is available")
        return self._output_schema

    def validate_json(self, json_str: str) -> Any:
        """Validate a JSON string against the output type. Returns the validated object, or raises
        a `ModelBehaviorError` if the JSON is invalid.
        """
        # _json.validate_json 用 TypeAdapter 校验模型返回的 JSON 文本。
        # 如果前面做过 wrapper，这里再把 response 字段拆出来给调用方。
        validated = _json.validate_json(json_str, self._type_adapter, partial=False)
        if self._is_wrapped:
            if not isinstance(validated, dict):
                _error_tracing.attach_error_to_current_span(
                    SpanError(
                        message="Invalid JSON",
                        data={"details": f"Expected a dict, got {type(validated)}"},
                    )
                )
                raise ModelBehaviorError(
                    f"Expected a dict, got {type(validated)} for JSON: {json_str}"
                )

            if _WRAPPER_DICT_KEY not in validated:
                _error_tracing.attach_error_to_current_span(
                    SpanError(
                        message="Invalid JSON",
                        data={"details": f"Could not find key {_WRAPPER_DICT_KEY} in JSON"},
                    )
                )
                raise ModelBehaviorError(
                    f"Could not find key {_WRAPPER_DICT_KEY} in JSON: {json_str}"
                )
            return validated[_WRAPPER_DICT_KEY]
        return validated

    def name(self) -> str:
        """The name of the output type."""
        return _type_to_str(self.output_type)


def _is_subclass_of_base_model_or_dict(t: Any) -> bool:
    # get_origin 用于处理泛型类型，例如 dict[str, int] 的 origin 是 dict。
    # If it's a generic alias, 'origin' will be the actual type, e.g. 'list'
    origin = get_origin(t)
    if origin is not None:
        return isinstance(origin, type) and issubclass(origin, BaseModel | dict)

    if not isinstance(t, type):
        return False

    return issubclass(t, BaseModel | dict)


def _type_to_str(t: Any) -> str:
    # 把复杂类型转成可读名字，用于 trace/schema 名称，例如 list[str]。
    origin = get_origin(t)
    args = get_args(t)

    if origin is None:
        # It's a simple type like `str`, `int`, etc.
        return getattr(t, "__name__", repr(t))
    elif args:
        args_str = ", ".join(_type_to_str(arg) for arg in args)
        origin_name = getattr(origin, "__name__", str(origin))
        return f"{origin_name}[{args_str}]"
    else:
        return str(t)
