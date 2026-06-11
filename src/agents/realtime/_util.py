from __future__ import annotations

from .config import RealtimeAudioFormat

PCM16_SAMPLE_RATE_HZ = 24_000
PCM16_SAMPLE_WIDTH_BYTES = 2
G711_SAMPLE_RATE_HZ = 8_000

# 学习提示：这里是实时音频长度估算工具。PCM16 和 G.711 的采样率不同，
# 需要用不同公式把字节数换算成播放毫秒数。


def calculate_audio_length_ms(format: RealtimeAudioFormat | None, audio_bytes: bytes) -> float:
    # 没有音频格式时默认按 PCM16 24kHz 估算，是 OpenAI realtime 常见格式。
    if not audio_bytes:
        return 0.0

    normalized_format = format.lower() if isinstance(format, str) else None

    if normalized_format and normalized_format.startswith("g711"):
        return (len(audio_bytes) / G711_SAMPLE_RATE_HZ) * 1000

    samples = len(audio_bytes) / PCM16_SAMPLE_WIDTH_BYTES
    return (samples / PCM16_SAMPLE_RATE_HZ) * 1000
