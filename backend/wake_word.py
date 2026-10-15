"""A.L.F.R.E.D. Wake-Word Engine.

Local, low-latency wake-word detection using openwakeword ONNX runtime
with fallback to Push-to-Talk and manual triggers.
"""

from __future__ import annotations

import logging
from typing import Optional
import numpy as np

logger = logging.getLogger("AlfredWakeWord")

try:
    import openwakeword
    from openwakeword.model import Model
except ImportError:
    openwakeword = None
    Model = None


class WakeWordDetector:
    """Manages local ONNX wake-word detection on 16kHz mono audio streams."""

    def __init__(
        self,
        wake_words: Optional[list[str]] = None,
        threshold: float = 0.5,
    ) -> None:
        self.wake_words = wake_words or ["hey alfred", "alexa"]
        self.threshold = threshold
        self.model: Optional[Model] = None
        self._is_ready = False
        self._manual_triggered = False

        self._initialize_model()

    def _initialize_model(self) -> None:
        """Initializes openwakeword ONNX models if installed."""
        if Model is None:
            logger.info("openwakeword not installed; running in fallback/PTT mode.")
            return

        try:
            # Initialize openwakeword with available models
            self.model = Model(inference_framework="onnx")
            self._is_ready = True
            logger.info("openwakeword ONNX models loaded successfully.")
        except Exception as e:
            logger.warning("Could not initialize openwakeword ONNX runtime: %s", e)
            self.model = None

    @property
    def is_ready(self) -> bool:
        """Returns True if the ONNX model is loaded and ready."""
        return self._is_ready

    def trigger_manually(self) -> None:
        """Simulates or forces a wake-word trigger (e.g. from Push-to-Talk)."""
        self._manual_triggered = True

    def process_pcm_chunk(self, pcm_chunk: bytes) -> bool:
        """Processes a 16kHz 16-bit PCM chunk and returns True if wake word detected.

        Args:
            pcm_chunk: Raw 16-bit PCM mono audio bytes.
        """
        if self._manual_triggered:
            self._manual_triggered = False
            return True

        if not self._is_ready or self.model is None or not pcm_chunk:
            return False

        try:
            # Convert PCM bytes to 16-bit signed numpy array
            audio_array = np.frombuffer(pcm_chunk, dtype=np.int16)
            prediction = self.model.predict(audio_array)

            # Check if any model score exceeds threshold
            for model_name, score in self.model.prediction_buffer.items():
                if score and score[-1] >= self.threshold:
                    logger.info("Wake-word detected [%s] with confidence %.2f", model_name, score[-1])
                    return True
        except Exception as e:
            logger.debug("Error processing audio frame for wake-word: %s", e)

        return False
