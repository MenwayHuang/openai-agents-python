from __future__ import annotations

# 中文学习注释：
# 这个文件负责把“普通 Python 函数”转换为“模型可调用工具”的 schema。
# 关键链路是：
# 1. inspect 读取函数签名；
# 2. get_type_hints 读取参数类型；
# 3. griffe 解析 docstring，提取函数说明和参数说明；
# 4. pydantic.create_model 动态创建参数模型；
# 5. 再由 Pydantic 生成 JSON Schema，发给 LLM 作为工具参数契约。
# 自研 agent-service 的工具系统也会需要类似能力：函数定义 -> 工具描述 -> 参数校验 -> 调用。

# 中文导入说明：
# - inspect 是官方反射库，可以读取函数参数、默认值、注解和签名。
# - re 用于正则解析 docstring 或参数说明。
# - griffe 是第三方文档解析库，专门读取 Python docstring 的结构化内容。
# - pydantic.create_model 可以运行时动态创建模型，这正是“函数参数 -> JSON Schema”的关键。
# - Field/FieldInfo 用于描述参数默认值、说明、约束等元信息。

import contextlib
import inspect
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal, get_args, get_origin, get_type_hints

# griffelib exposes the `griffe` package at runtime but currently does not ship typing markers.
from griffe import Docstring, DocstringSectionKind  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, create_model
from pydantic.fields import FieldInfo

from .exceptions import UserError
from .run_context import RunContextWrapper
from .strict_schema import ensure_strict_json_schema
from .tool_context import ToolContext


@dataclass
class FuncSchema:
    """
    Captures the schema for a python function, in preparation for sending it to an LLM as a tool.
    """
    # FuncSchema 是 function_tool 装饰器背后的核心结果对象。
    # 它同时保存“给模型看的 JSON Schema”和“回到 Python 调用原函数所需的信息”。

    name: str
    """The name of the function."""
    description: str | None
    """The description of the function."""
    params_pydantic_model: type[BaseModel]
    """A Pydantic model that represents the function's parameters."""
    params_json_schema: dict[str, Any]
    """The JSON schema for the function's parameters, derived from the Pydantic model."""
    signature: inspect.Signature
    """The signature of the function."""
    takes_context: bool = False
    """Whether the function takes a RunContextWrapper argument (must be the first argument)."""
    strict_json_schema: bool = True
    """Whether the JSON schema is in strict mode. We **strongly** recommend setting this to True,
    as it increases the likelihood of correct JSON input."""

    def to_call_args(self, data: BaseModel) -> tuple[list[Any], dict[str, Any]]:
        """
        Converts validated data from the Pydantic model into (args, kwargs), suitable for calling
        the original function.
        """
        # 模型传入 JSON -> Pydantic 校验成 BaseModel -> 这里再还原成 Python 函数调用参数。
        # 返回 (args, kwargs)，最终可以用 func(*args, **kwargs) 调用原始函数。
        positional_args: list[Any] = []
        keyword_args: dict[str, Any] = {}
        seen_var_positional = False

        # Use enumerate() so we can skip the first parameter if it's context.
        for idx, (name, param) in enumerate(self.signature.parameters.items()):
            # inspect.Signature.Parameter.kind 会告诉我们参数类型：
            # 普通位置参数、关键字参数、*args、**kwargs、keyword-only 等。
            # If the function takes a RunContextWrapper and this is the first parameter, skip it.
            if self.takes_context and idx == 0:
                continue

            value = getattr(data, name, None)
            if param.kind == param.VAR_POSITIONAL:
                # e.g. *args: extend positional args and mark that *args is now seen
                positional_args.extend(value or [])
                seen_var_positional = True
            elif param.kind == param.VAR_KEYWORD:
                # e.g. **kwargs handling
                keyword_args.update(value or {})
            elif param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
                # Before *args, add to positional args. After *args, add to keyword args.
                if not seen_var_positional:
                    positional_args.append(value)
                else:
                    keyword_args[name] = value
            else:
                # For KEYWORD_ONLY parameters, always use keyword args.
                keyword_args[name] = value
        return positional_args, keyword_args


@dataclass
class FuncDocumentation:
    """Contains metadata about a Python function, extracted from its docstring."""
    # 这只是从 docstring 里解析出来的“文档信息”，还不是最终 JSON Schema。

    name: str
    """The name of the function, via `__name__`."""
    description: str | None
    """The description of the function, derived from the docstring."""
    param_descriptions: dict[str, str] | None
    """The parameter descriptions of the function, derived from the docstring."""


DocstringStyle = Literal["google", "numpy", "sphinx"]
# Literal 表示这个变量只能取几个固定字符串之一，常用于限制配置值。


# As of Feb 2025, the automatic style detection in griffe is an Insiders feature. This
# code approximates it.
def _detect_docstring_style(doc: str) -> DocstringStyle:
    # griffe 的自动识别能力在当时不是开放功能，所以 SDK 用正则做简易判断。
    # 支持 Google / Numpy / Sphinx 三种常见 Python 文档风格。
    scores: dict[DocstringStyle, int] = {"sphinx": 0, "numpy": 0, "google": 0}

    # Sphinx style detection: look for :param, :type, :return:, and :rtype:
    sphinx_patterns = [r"^:param\s", r"^:type\s", r"^:return:", r"^:rtype:"]
    for pattern in sphinx_patterns:
        if re.search(pattern, doc, re.MULTILINE):
            scores["sphinx"] += 1

    # Numpy style detection: look for headers like 'Parameters', 'Returns', or 'Yields' followed by
    # a dashed underline
    numpy_patterns = [
        r"^Parameters\s*\n\s*-{3,}",
        r"^Returns\s*\n\s*-{3,}",
        r"^Yields\s*\n\s*-{3,}",
    ]
    for pattern in numpy_patterns:
        if re.search(pattern, doc, re.MULTILINE):
            scores["numpy"] += 1

    # Google style detection: look for section headers with a trailing colon
    google_patterns = [r"^(Args|Arguments):", r"^(Returns):", r"^(Raises):"]
    for pattern in google_patterns:
        if re.search(pattern, doc, re.MULTILINE):
            scores["google"] += 1

    max_score = max(scores.values())
    if max_score == 0:
        return "google"

    # Priority order: sphinx > numpy > google in case of tie
    styles: list[DocstringStyle] = ["sphinx", "numpy", "google"]

    for style in styles:
        if scores[style] == max_score:
            return style

    return "google"


@contextlib.contextmanager
def _suppress_griffe_logging():
    # Suppresses warnings about missing annotations for params
    # @contextmanager 可以把一个生成器函数变成 with 上下文管理器。
    # yield 前是进入 with 的逻辑，finally 里是退出 with 的清理逻辑。
    logger = logging.getLogger("griffe")
    previous_level = logger.getEffectiveLevel()
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous_level)


def generate_func_documentation(
    func: Callable[..., Any], style: DocstringStyle | None = None
) -> FuncDocumentation:
    """
    Extracts metadata from a function docstring, in preparation for sending it to an LLM as a tool.

    Args:
        func: The function to extract documentation from.
        style: The style of the docstring to use for parsing. If not provided, we will attempt to
            auto-detect the style.

    Returns:
        A FuncDocumentation object containing the function's name, description, and parameter
        descriptions.
    """
    # inspect.getdoc 会读取函数 docstring，并自动处理缩进。
    # griffe.Docstring 负责把自然语言文档拆成 text、parameters 等结构化 section。
    name = func.__name__
    doc = inspect.getdoc(func)
    if not doc:
        return FuncDocumentation(name=name, description=None, param_descriptions=None)

    with _suppress_griffe_logging():
        docstring = Docstring(doc, lineno=1, parser=style or _detect_docstring_style(doc))
        parsed = docstring.parse()

    description: str | None = next(
        (section.value for section in parsed if section.kind == DocstringSectionKind.text), None
    )

    param_descriptions: dict[str, str] = {
        param.name: param.description
        for section in parsed
        if section.kind == DocstringSectionKind.parameters
        for param in section.value
    }

    return FuncDocumentation(
        name=func.__name__,
        description=description,
        param_descriptions=param_descriptions or None,
    )


def _strip_annotated(annotation: Any) -> tuple[Any, tuple[Any, ...]]:
    """Returns the underlying annotation and any metadata from typing.Annotated."""
    # Annotated[int, "用户年龄"] 这种写法会把类型 int 和额外元数据放在一起。
    # 给模型生成工具 schema 时，字符串元数据可以作为参数描述。

    metadata: tuple[Any, ...] = ()
    ann = annotation

    while get_origin(ann) is Annotated:
        args = get_args(ann)
        if not args:
            break
        ann = args[0]
        metadata = (*metadata, *args[1:])

    return ann, metadata


def _extract_description_from_metadata(metadata: tuple[Any, ...]) -> str | None:
    """Extracts a human readable description from Annotated metadata if present."""

    for item in metadata:
        if isinstance(item, str):
            return item
    return None


def _extract_field_info_from_metadata(metadata: tuple[Any, ...]) -> FieldInfo | None:
    """Returns the first FieldInfo in Annotated metadata, or None."""
    # Pydantic 的 Field(...) 可以携带 description、范围约束、默认值等信息。
    # 如果用户写 Annotated[int, Field(gt=0)]，这里会把 FieldInfo 提出来。

    for item in metadata:
        if isinstance(item, FieldInfo):
            return item
    return None


def function_schema(
    func: Callable[..., Any],
    docstring_style: DocstringStyle | None = None,
    name_override: str | None = None,
    description_override: str | None = None,
    use_docstring_info: bool = True,
    strict_json_schema: bool = True,
) -> FuncSchema:
    """
    Given a Python function, extracts a `FuncSchema` from it, capturing the name, description,
    parameter descriptions, and other metadata.

    Args:
        func: The function to extract the schema from.
        docstring_style: The style of the docstring to use for parsing. If not provided, we will
            attempt to auto-detect the style.
        name_override: If provided, use this name instead of the function's `__name__`.
        description_override: If provided, use this description instead of the one derived from the
            docstring.
        use_docstring_info: If True, uses the docstring to generate the description and parameter
            descriptions.
        strict_json_schema: Whether the JSON schema is in strict mode. If True, we'll ensure that
            the schema adheres to the "strict" standard the OpenAI API expects. We **strongly**
            recommend setting this to True, as it increases the likelihood of the LLM producing
            correct JSON input.

    Returns:
        A `FuncSchema` object containing the function's name, description, parameter descriptions,
        and other metadata.
    """

    # 1. Grab docstring info
    # 第一步：提取函数说明和参数说明，给模型理解工具用途。
    if use_docstring_info:
        doc_info = generate_func_documentation(func, docstring_style)
        param_descs = dict(doc_info.param_descriptions or {})
    else:
        doc_info = None
        param_descs = {}

    # include_extras=True 会保留 Annotated 里的附加信息；
    # 不加的话 Python 会只返回最底层类型，丢掉参数描述/约束。
    type_hints_with_extras = get_type_hints(func, include_extras=True)
    type_hints: dict[str, Any] = {}
    annotated_param_descs: dict[str, str] = {}
    param_metadata: dict[str, tuple[Any, ...]] = {}

    for name, annotation in type_hints_with_extras.items():
        if name == "return":
            continue

        # 把 Annotated[T, ...] 拆成 T 和 metadata，便于后续创建 Pydantic 字段。
        stripped_ann, metadata = _strip_annotated(annotation)
        type_hints[name] = stripped_ann
        param_metadata[name] = metadata

        description = _extract_description_from_metadata(metadata)
        if description is not None:
            annotated_param_descs[name] = description

    for name, description in annotated_param_descs.items():
        param_descs.setdefault(name, description)

    # Ensure name_override takes precedence even if docstring info is disabled.
    func_name = name_override or (doc_info.name if doc_info else func.__name__)

    # 2. Inspect function signature and get type hints
    # 第二步：读取函数签名，识别 context 参数和所有可暴露给模型的业务参数。
    sig = inspect.signature(func)
    params = list(sig.parameters.items())
    takes_context = False
    filtered_params = []

    if params:
        first_name, first_param = params[0]
        # Prefer the evaluated type hint if available
        ann = type_hints.get(first_name, first_param.annotation)
        if ann != inspect._empty:
            origin = get_origin(ann) or ann
            if origin is RunContextWrapper or origin is ToolContext:
                # 约定：context 参数只能放第一个，且不会暴露给模型填写。
                takes_context = True  # Mark that the function takes context
            else:
                filtered_params.append((first_name, first_param))
        else:
            filtered_params.append((first_name, first_param))

    # For parameters other than the first, raise error if any use RunContextWrapper or ToolContext.
    for name, param in params[1:]:
        ann = type_hints.get(name, param.annotation)
        if ann != inspect._empty:
            origin = get_origin(ann) or ann
            if origin is RunContextWrapper or origin is ToolContext:
                # 如果 context 不在第一个位置，就拒绝，避免工具函数调用时参数错位。
                raise UserError(
                    f"RunContextWrapper/ToolContext param found at non-first position in function"
                    f" {func.__name__}"
                )
        filtered_params.append((name, param))

    # We will collect field definitions for create_model as a dict:
    #   field_name -> (type_annotation, default_value_or_Field(...))
    fields: dict[str, Any] = {}

    for name, param in filtered_params:
        ann = type_hints.get(name, param.annotation)
        default = param.default

        # If there's no type hint, assume `Any`
        # 没写类型时退化为 Any，schema 约束会变弱，所以正式项目里建议工具参数都写类型。
        if ann == inspect._empty:
            ann = Any

        # If a docstring param description exists, use it
        field_description = param_descs.get(name, None)

        # Handle different parameter kinds
        if param.kind == param.VAR_POSITIONAL:
            # e.g. *args: extend positional args
            # *args 在 JSON Schema 里没有原生位置参数概念，所以这里统一建模成 list。
            if get_origin(ann) is tuple:
                # e.g. def foo(*args: tuple[int, ...]) -> treat as List[int]
                args_of_tuple = get_args(ann)
                if len(args_of_tuple) == 2 and args_of_tuple[1] is Ellipsis:
                    ann = list[args_of_tuple[0]]  # type: ignore
                else:
                    ann = list[Any]
            else:
                # If user wrote *args: int, treat as List[int]
                ann = list[ann]  # type: ignore

            # Default factory to empty list
            fields[name] = (
                ann,
                Field(default_factory=list, description=field_description),
            )

        elif param.kind == param.VAR_KEYWORD:
            # **kwargs handling
            # **kwargs 统一建模成 dict，模型会输出一个对象。
            if get_origin(ann) is dict:
                # e.g. def foo(**kwargs: dict[str, int])
                dict_args = get_args(ann)
                if len(dict_args) == 2:
                    ann = dict[dict_args[0], dict_args[1]]  # type: ignore
                else:
                    ann = dict[str, Any]
            else:
                # e.g. def foo(**kwargs: int) -> Dict[str, int]
                ann = dict[str, ann]  # type: ignore

            fields[name] = (
                ann,
                Field(default_factory=dict, description=field_description),
            )

        else:
            # Normal parameter
            # 普通参数会根据“是否有默认值”决定 required/optional。
            metadata = param_metadata.get(name, ())
            field_info_from_annotated = _extract_field_info_from_metadata(metadata)

            if field_info_from_annotated is not None:
                # 如果 Annotated 里已经有 Field(...)，要和 docstring/默认值合并，而不是覆盖掉。
                merged = FieldInfo.merge_field_infos(
                    field_info_from_annotated,
                    description=field_description or field_info_from_annotated.description,
                )
                if default != inspect._empty and not isinstance(default, FieldInfo):
                    merged = FieldInfo.merge_field_infos(merged, default=default)
                elif isinstance(default, FieldInfo):
                    merged = FieldInfo.merge_field_infos(merged, default)
                fields[name] = (ann, merged)
            elif default == inspect._empty:
                # Required field
                # Field(...): Pydantic 里三个点 Ellipsis 表示必填字段。
                fields[name] = (
                    ann,
                    Field(..., description=field_description),
                )
            elif isinstance(default, FieldInfo):
                # Parameter with a default value that is a Field(...)
                fields[name] = (
                    ann,
                    FieldInfo.merge_field_infos(
                        default, description=field_description or default.description
                    ),
                )
            else:
                # Parameter with a default value
                fields[name] = (
                    ann,
                    Field(default=default, description=field_description),
                )

    # 3. Dynamically build a Pydantic model
    # create_model 是 Pydantic 的动态建模能力：运行时创建一个 BaseModel 子类。
    # 这就是为什么无需手写参数模型，也能把任意函数变成结构化工具。
    dynamic_model = create_model(f"{func_name}_args", __base__=BaseModel, **fields)

    # 4. Build JSON schema from that model
    # Pydantic 模型可以导出 JSON Schema；OpenAI API 用它约束工具调用参数。
    json_schema = dynamic_model.model_json_schema()
    if strict_json_schema:
        # strict schema 会收紧 additionalProperties 等规则，提升模型输出可校验概率。
        json_schema = ensure_strict_json_schema(json_schema)

    # 5. Return as a FuncSchema dataclass
    return FuncSchema(
        name=func_name,
        # Ensure description_override takes precedence even if docstring info is disabled.
        description=description_override or (doc_info.description if doc_info else None),
        params_pydantic_model=dynamic_model,
        params_json_schema=json_schema,
        signature=sig,
        takes_context=takes_context,
        strict_json_schema=strict_json_schema,
    )
