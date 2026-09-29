"""Offline voice recognition for Karina using sounddevice and Vosk."""

from __future__ import annotations

import json
import os
import queue
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from paths import resource_dirs

try:
    import numpy as np
    import sounddevice as sd
except ImportError:  # pragma: no cover
    np = None
    sd = None

try:
    from vosk import KaldiRecognizer, Model
except ImportError:  # pragma: no cover
    KaldiRecognizer = None
    Model = None

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"


def find_vosk_model() -> Optional[Path]:
    """Locate a Vosk model via KARINA_VOSK_MODEL or vosk-model-* next to the app."""
    env_path = os.environ.get("KARINA_VOSK_MODEL")
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_dir():
            return path

    for folder in resource_dirs():
        for candidate in sorted(folder.glob("vosk-model-*")):
            if candidate.is_dir():
                return candidate

    return None


def is_voice_available() -> Tuple[bool, str]:
    """Return whether voice input is ready and a status message."""
    if sd is None or np is None:
        return False, "Voice input requires sounddevice. Install with `pip install sounddevice`."

    if Model is None or KaldiRecognizer is None:
        return False, "Voice input requires vosk. Install with `pip install vosk`."

    model_path = find_vosk_model()
    if model_path is None:
        return (
            False,
            "No Vosk model found. Set KARINA_VOSK_MODEL or download a vosk-model-* folder "
            "into the project directory.",
        )

    return True, f"Voice input ready (model: {model_path.name})."


class VoiceRecognizer:
    """Record audio from the default microphone and transcribe with Vosk."""

    def __init__(self) -> None:
        self._recording = False
        self._stream: Optional[sd.InputStream] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._frames: List[np.ndarray] = []
        self._model: Optional[Model] = None
        self._lock = threading.Lock()
        self.device_index: Optional[int] = None

    def set_device(self, device_index: Optional[int]) -> None:
        self.device_index = device_index

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        model_path = find_vosk_model()
        if model_path is None:
            raise RuntimeError("No Vosk model found.")
        self._model = Model(str(model_path))

    def _audio_callback(self, indata, frames, time_info, status) -> None:  # noqa: ANN001
        if status:
            pass
        self._audio_queue.put(indata.copy())

    def start_recording(self) -> None:
        """Begin capturing microphone audio."""
        if sd is None or np is None:
            raise RuntimeError("sounddevice is not installed.")

        with self._lock:
            if self._recording:
                return

            self._frames = []
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except queue.Empty:
                    break

            stream_kwargs = {
                "samplerate": SAMPLE_RATE,
                "channels": CHANNELS,
                "dtype": DTYPE,
                "callback": self._audio_callback,
            }
            if self.device_index is not None:
                stream_kwargs["device"] = self.device_index
            self._stream = sd.InputStream(**stream_kwargs)
            self._stream.start()
            self._recording = True

    def stop_recording(self) -> str:
        """Stop capturing and return the transcribed text."""
        if sd is None or np is None:
            raise RuntimeError("sounddevice is not installed.")

        with self._lock:
            if not self._recording:
                return ""

            self._recording = False
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            while not self._audio_queue.empty():
                try:
                    self._frames.append(self._audio_queue.get_nowait())
                except queue.Empty:
                    break

        if not self._frames:
            return ""

        audio = np.concatenate(self._frames, axis=0)
        audio_bytes = audio.tobytes()

        self._ensure_model()
        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE)
        recognizer.AcceptWaveform(audio_bytes)
        result = json.loads(recognizer.FinalResult())
        return (result.get("text") or "").strip()


WAKE_PHRASES = ("hey karina", "okay karina", "ok karina", "hi karina")


class WakeWordListener:
    """Listen for a wake phrase, then capture the following command."""

    def __init__(
        self,
        recognizer: VoiceRecognizer,
        on_command: Callable[[str], None],
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.recognizer = recognizer
        self.on_command = on_command
        self.on_status = on_status
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._paused.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def pause(self) -> None:
        self._paused.set()

    def resume(self) -> None:
        self._paused.clear()

    def _notify(self, message: str) -> None:
        if self.on_status:
            self.on_status(message)

    def _run(self) -> None:
        if sd is None or np is None:
            return
        try:
            self.recognizer._ensure_model()
        except Exception as exc:
            self._notify(f"Wake word unavailable: {exc}")
            return

        audio_queue: queue.Queue = queue.Queue()

        def callback(indata, frames, time_info, status) -> None:  # noqa: ANN001
            if not self._paused.is_set():
                audio_queue.put(bytes(indata))

        stream_kwargs = {
            "samplerate": SAMPLE_RATE,
            "channels": CHANNELS,
            "dtype": DTYPE,
            "callback": callback,
            "blocksize": int(SAMPLE_RATE * 0.25),
        }
        if self.recognizer.device_index is not None:
            stream_kwargs["device"] = self.recognizer.device_index

        try:
            stream = sd.RawInputStream(**stream_kwargs)
        except Exception as exc:
            self._notify(f"Wake word microphone error: {exc}")
            return

        recognizer = KaldiRecognizer(self.recognizer._model, SAMPLE_RATE)
        capturing = False
        command_chunks: list[str] = []
        silent_checks = 0
        self._notify("Wake word listening. Say 'hey Karina'.")

        with stream:
            while not self._stop.is_set():
                try:
                    data = audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue

                if self._paused.is_set():
                    capturing = False
                    command_chunks = []
                    continue

                if recognizer.AcceptWaveform(data):
                    text = (json.loads(recognizer.Result()).get("text") or "").strip().lower()
                else:
                    text = (json.loads(recognizer.PartialResult()).get("partial") or "").strip().lower()

                if not capturing:
                    if any(phrase in text for phrase in WAKE_PHRASES):
                        capturing = True
                        command_chunks = []
                        silent_checks = 0
                        self._notify("Wake word heard. Listening for a command...")
                    continue

                if text:
                    silent_checks = 0
                    spoken = text
                    for phrase in WAKE_PHRASES:
                        spoken = spoken.replace(phrase, " ")
                    spoken = " ".join(spoken.split())
                    if spoken:
                        command_chunks.append(spoken)
                else:
                    silent_checks += 1

                if silent_checks >= 4 or len(command_chunks) >= 12:
                    command = command_chunks[-1] if command_chunks else ""
                    capturing = False
                    command_chunks = []
                    silent_checks = 0
                    if command:
                        self.on_command(command)
                    else:
                        self._notify("Wake word heard, but I didn't catch a command.")
                    self._notify("Wake word listening. Say 'hey Karina'.")
