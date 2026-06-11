from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..model_settings import ModelSettings

# 学习提示：trace 记录要有排障价值，但不能泄露密钥、账号、查询参数。
# 这个文件负责把模型配置转换成可安全写入 tracing 的字典。


def sanitize_url_for_trace(url: object) -> str:
    """Return a URL safe for tracing by removing auth material and request parameters."""
    try:
        parts = urlsplit(str(url))
    except ValueError:
        return ""

    netloc = parts.netloc.rsplit("@", 1)[-1]
    # 丢弃 query/fragment，且去掉 user:password@host 里的认证材料。
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def model_config_for_trace(
    model_settings: ModelSettings,
    *,
    base_url: object | None = None,
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # ModelSettings.to_traceable_dict() 会过滤掉不适合进入 trace 的字段。
    config = model_settings.to_traceable_dict()
    if base_url is not None:
        config["base_url"] = sanitize_url_for_trace(base_url)
    if extra_config:
        config.update(extra_config)
    return config
