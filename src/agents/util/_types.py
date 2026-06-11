from collections.abc import Awaitable
from typing import TypeAlias

from typing_extensions import TypeVar

T = TypeVar("T")
MaybeAwaitable: TypeAlias = Awaitable[T] | T

# 学习提示：MaybeAwaitable[T] 表示“可以直接返回 T，也可以返回 Awaitable[T]”。
# 这让 hook/callback 既支持普通函数，也支持 async 函数。
