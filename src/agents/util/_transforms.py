import re

from ..logger import logger

# 学习提示：模型函数调用的 tool name 只能包含安全字符。
# 这个工具把任意名称转换成 function-call 友好的 snake_case 风格。


def transform_string_function_style(name: str) -> str:
    transformed_name = name.replace(" ", "_")

    transformed_name = re.sub(r"[^a-zA-Z0-9_]", "_", transformed_name)
    final_name = transformed_name.lower()

    if transformed_name != name:
        logger.warning(
            f"Tool name {name!r} contains invalid characters for function calling and has been "
            f"transformed to {final_name!r}. Please use only letters, digits, and underscores "
            "to avoid potential naming conflicts."
        )

    return final_name
