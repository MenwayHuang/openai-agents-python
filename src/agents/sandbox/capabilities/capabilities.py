"""中文学习提示：定义默认启用的沙箱能力组合。

当前默认能力是 Filesystem、Shell、Compaction，也就是模型默认能看图/打补丁、
执行命令，以及在上下文过长时做压缩。后续如果我们给 PPT Agent 做隔离执行环境，
这里的模式很值得参考：把能力显式列出来，而不是让 agent 随意访问所有系统资源。
"""

from .capability import Capability
from .compaction import Compaction
from .filesystem import Filesystem
from .shell import Shell


class Capabilities:
    """沙箱默认能力的工厂类。"""

    @classmethod
    def default(cls) -> list[Capability]:
        """返回一次会话默认挂载给 agent 的能力列表。"""

        return [Filesystem(), Shell(), Compaction()]
