from ..exceptions import AgentsException

# 学习提示：语音模块的专用异常，继承 SDK 统一异常基类，便于调用方统一捕获 AgentsException。


class STTWebsocketConnectionError(AgentsException):
    """Exception raised when the STT websocket connection fails."""

    def __init__(self, message: str):
        self.message = message
