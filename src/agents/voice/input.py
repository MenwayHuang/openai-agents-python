from __future__ import annotations

# 中文导入说明：
# - base64 用来把音频 bytes 编成字符串，便于通过 JSON 或 API 传输。
# - io.BytesIO 是内存中的“文件对象”，不用落盘也能把音频交给上传接口。
# - wave 是 Python 官方 WAV 文件读写库，用来把 numpy PCM buffer 包成 wav 格式。
# - `.imports` 里的 np/npt 来自 numpy：np 是数组计算库，npt 是 numpy 的类型注解。

import asyncio
import base64
import io
import wave
from dataclasses import dataclass
from typing import cast

from ..exceptions import UserError
from .imports import np, npt

DEFAULT_SAMPLE_RATE = 24000

# 学习提示：这个文件把音频输入统一成模型可消费的格式。
# numpy 数组负责承载 PCM 数据，wave/io.BytesIO 用来生成内存中的 wav 文件。


def _buffer_to_audio_file(
    buffer: npt.NDArray[np.int16 | np.float32 | np.float64],
    frame_rate: int = DEFAULT_SAMPLE_RATE,
    sample_width: int = 2,
    channels: int = 1,
) -> tuple[str, io.BytesIO, str]:
    # float32 音频通常在 -1.0~1.0，发送前要裁剪并转换为 int16 PCM。
    if buffer.dtype == np.float32:
        # convert to int16
        buffer = np.clip(buffer, -1.0, 1.0)
        buffer = (buffer * 32767).astype(np.int16)
    elif buffer.dtype != np.int16:
        raise UserError("Buffer must be a numpy array of int16 or float32")

    audio_file = io.BytesIO()
    with wave.open(audio_file, "w") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(frame_rate)
        wav_file.writeframes(buffer.tobytes())
        audio_file.seek(0)

    # (filename, bytes, content_type)
    return ("audio.wav", audio_file, "audio/wav")


@dataclass
class AudioInput:
    """Static audio to be used as input for the VoicePipeline."""

    buffer: npt.NDArray[np.int16 | np.float32]
    """
    A buffer containing the audio data for the agent. Must be a numpy array of int16 or float32.
    """

    frame_rate: int = DEFAULT_SAMPLE_RATE
    """The sample rate of the audio data. Defaults to 24000."""

    sample_width: int = 2
    """The sample width of the audio data. Defaults to 2."""

    channels: int = 1
    """The number of channels in the audio data. Defaults to 1."""

    def to_audio_file(self) -> tuple[str, io.BytesIO, str]:
        """Returns a tuple of (filename, bytes, content_type)"""
        return _buffer_to_audio_file(self.buffer, self.frame_rate, self.sample_width, self.channels)

    def to_base64(self) -> str:
        """Returns the audio data as a base64 encoded string."""
        if self.buffer.dtype == np.float32:
            # convert to int16 without mutating the caller's buffer
            int16_buffer = (np.clip(self.buffer, -1.0, 1.0) * 32767).astype(np.int16)
        elif self.buffer.dtype == np.int16:
            int16_buffer = cast("npt.NDArray[np.int16]", self.buffer)
        else:
            raise UserError("Buffer must be a numpy array of int16 or float32")

        return base64.b64encode(int16_buffer.tobytes()).decode("utf-8")


class StreamedAudioInput:
    """Audio input represented as a stream of audio data. You can pass this to the `VoicePipeline`
    and then push audio data into the queue using the `add_audio` method.
    """

    def __init__(self):
        # asyncio.Queue 用于生产者/消费者模型：外部不断 add_audio，pipeline 异步读取。
        self.queue: asyncio.Queue[npt.NDArray[np.int16 | np.float32] | None] = asyncio.Queue()

    async def add_audio(self, audio: npt.NDArray[np.int16 | np.float32] | None):
        """Adds more audio data to the stream.

        Args:
            audio: The audio data to add. Must be a numpy array of int16 or float32 or None.
              If None passed, it indicates the end of the stream.
        """
        await self.queue.put(audio)
