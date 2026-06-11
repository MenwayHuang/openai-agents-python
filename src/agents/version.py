"""中文学习提示：这里统一暴露 openai-agents 包版本。

运行源码但没有安装成 pip 包时，会落到 0.0.0；排查环境时可以先看这里。
"""

import importlib.metadata

try:
    __version__ = importlib.metadata.version("openai-agents")
except importlib.metadata.PackageNotFoundError:
    # Fallback if running from source without being installed
    __version__ = "0.0.0"
