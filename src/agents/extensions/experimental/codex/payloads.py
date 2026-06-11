"""Codex payload 的 dict-like 适配基类。

学习提示：_DictLike 让 dataclass 同时支持属性访问和部分 dict 访问方法，
这样旧代码或工具链按 item[\"type\"] / item.get(...) 读取时也能兼容。
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable
from typing import Any, cast


class _DictLike:
    def __getitem__(self, key: str) -> Any:
        if key in self._field_names():
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._field_names():
            return getattr(self, key)
        return default

    def __contains__(self, key: object) -> bool:
        if not isinstance(key, str):
            return False
        return key in self._field_names()

    def keys(self) -> Iterable[str]:
        return iter(self._field_names())

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(cast(Any, self))

    def _field_names(self) -> list[str]:
        return [field.name for field in dataclasses.fields(cast(Any, self))]
