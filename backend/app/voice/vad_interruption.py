import math
import struct
from typing import Callable, Optional

class VoiceActivityDetector:
    """
    Real-time energy and amplitude-based VAD (Voice Activity Detector)
    for raw PCM 16-bit 16kHz audio frames.
    Detects customer speech start/stop for barge-in interruption.
    """

    def __init__(self, energy_threshold: float = 0.015, min_speech_duration_ms: int = 120):
        self.energy_threshold = energy_threshold
        self.min_speech_frames = int(min_speech_duration_ms / 20)  # assuming 20ms frames
        self.consecutive_speech_frames = 0
        self.is_speech_active = False

    def calculate_rms(self, pcm_bytes: bytes) -> float:
        """Calculate Root Mean Square energy of 16-bit signed PCM audio bytes."""
        count = len(pcm_bytes) // 2
        if count == 0:
            return 0.0

        format_str = f"<{count}h"
        try:
            shorts = struct.unpack(format_str, pcm_bytes)
            sum_squares = sum((sample / 32768.0) ** 2 for sample in shorts)
            return math.sqrt(sum_squares / count)
        except Exception:
            return 0.0

    def process_frame(self, pcm_bytes: bytes) -> bool:
        """
        Process an audio chunk.
        Returns True if confident human speech is active (triggering barge-in).
        """
        rms = self.calculate_rms(pcm_bytes)
        if rms > self.energy_threshold:
            self.consecutive_speech_frames += 1
            if self.consecutive_speech_frames >= self.min_speech_frames:
                self.is_speech_active = True
                return True
        else:
            self.consecutive_speech_frames = max(0, self.consecutive_speech_frames - 1)
            if self.consecutive_speech_frames == 0:
                self.is_speech_active = False

        return False

    def reset(self):
        self.consecutive_speech_frames = 0
        self.is_speech_active = False


class InterruptionCoordinator:
    """
    Coordinates barge-in interruption across the voice pipeline.
    When caller speech is detected while AI is speaking:
    1. Triggers cancellation callback
    2. Drops outbound audio queues
    3. Notifies frontend/telephony client to flush playback buffer
    """

    def __init__(self, on_barge_in: Optional[Callable[[], None]] = None):
        self.vad = VoiceActivityDetector()
        self.ai_is_speaking = False
        self.on_barge_in = on_barge_in
        self.interruption_count = 0

    def set_ai_speaking(self, speaking: bool):
        self.ai_is_speaking = speaking
        if not speaking:
            self.vad.reset()

    def handle_incoming_pcm(self, pcm_bytes: bytes) -> bool:
        """
        Returns True if this frame causes a barge-in interruption.
        """
        is_speech = self.vad.process_frame(pcm_bytes)
        if is_speech and self.ai_is_speaking:
            self.interruption_count += 1
            self.ai_is_speaking = False
            if self.on_barge_in:
                self.on_barge_in()
            return True
        return False
