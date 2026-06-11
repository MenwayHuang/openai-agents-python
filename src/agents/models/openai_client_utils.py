from __future__ import annotations

from urllib.parse import urlsplit

from openai import AsyncOpenAI

# 学习提示：这些函数用于判断客户端是否真正指向官方 OpenAI 端点。
# SDK 在官方端点上会开启某些默认能力；面对兼容 Provider 时则更保守。


def is_official_openai_base_url(base_url: object, *, websocket: bool = False) -> bool:
    # 普通 HTTP 期望 https://api.openai.com，WebSocket 期望 wss://api.openai.com。
    parsed = urlsplit(str(base_url))
    expected_scheme = "wss" if websocket else "https"
    return parsed.scheme == expected_scheme and parsed.hostname == "api.openai.com"


def is_official_openai_client(client: AsyncOpenAI) -> bool:
    # AsyncOpenAI 是 openai-python 的异步客户端；base_url 可被用户替换成代理或兼容服务。
    base_url = getattr(client, "base_url", None)
    if base_url is None:
        return False
    return is_official_openai_base_url(base_url)
