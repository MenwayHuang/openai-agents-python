"""Voice 子包的公开导出入口。

学习提示：voice 是“语音流水线”能力，包含 STT(语音转文字)、Agent workflow、
TTS(文字转语音) 和流式音频结果。它和 realtime 不同：voice 更像分阶段 pipeline，
realtime 更像持续双向会话。
"""

from .events import VoiceStreamEvent, VoiceStreamEventAudio, VoiceStreamEventLifecycle
from .exceptions import STTWebsocketConnectionError
from .input import AudioInput, StreamedAudioInput
from .model import (
    StreamedTranscriptionSession,
    STTModel,
    STTModelSettings,
    TTSModel,
    TTSModelSettings,
    TTSVoice,
    VoiceModelProvider,
)
from .models.openai_model_provider import OpenAIVoiceModelProvider
from .models.openai_stt import OpenAISTTModel, OpenAISTTTranscriptionSession
from .models.openai_tts import OpenAITTSModel
from .pipeline import VoicePipeline
from .pipeline_config import VoicePipelineConfig
from .result import StreamedAudioResult
from .utils import get_sentence_based_splitter
from .workflow import (
    SingleAgentVoiceWorkflow,
    SingleAgentWorkflowCallbacks,
    VoiceWorkflowBase,
    VoiceWorkflowHelper,
)

__all__ = [
    "AudioInput",
    "StreamedAudioInput",
    "STTModel",
    "STTModelSettings",
    "TTSModel",
    "TTSModelSettings",
    "TTSVoice",
    "VoiceModelProvider",
    "StreamedAudioResult",
    "SingleAgentVoiceWorkflow",
    "OpenAIVoiceModelProvider",
    "OpenAISTTModel",
    "OpenAITTSModel",
    "VoiceStreamEventAudio",
    "VoiceStreamEventLifecycle",
    "VoiceStreamEvent",
    "VoicePipeline",
    "VoicePipelineConfig",
    "get_sentence_based_splitter",
    "VoiceWorkflowHelper",
    "VoiceWorkflowBase",
    "SingleAgentWorkflowCallbacks",
    "StreamedTranscriptionSession",
    "OpenAISTTTranscriptionSession",
    "STTWebsocketConnectionError",
]
