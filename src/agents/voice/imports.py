try:
    # voice 是可选依赖：numpy 处理音频数组，websockets 用于流式 STT/TTS 连接。
    import numpy as np
    import numpy.typing as npt
    import websockets
except ImportError as _e:
    raise ImportError(
        "`numpy` + `websockets` are required to use voice. You can install them via the optional "
        "dependency group: `pip install 'openai-agents[voice]'`."
    ) from _e

__all__ = ["np", "npt", "websockets"]
