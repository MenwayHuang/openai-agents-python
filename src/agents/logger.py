"""SDK 统一 logger。

中文学习说明：
- 所有模块共用 `openai.agents` 这个 logger 名称，应用层可以统一配置日志级别和 handler。
- 生产环境要结合 `_debug.py` 的脱敏开关，避免把模型输入、工具参数、用户隐私写入日志。
"""

import logging

logger = logging.getLogger("openai.agents")
