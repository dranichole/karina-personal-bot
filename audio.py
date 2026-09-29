"""Karina audio helpers for device listing and selection."""

from __future__ import annotations

from typing import Optional

from fuzzy_match import resolve_fuzzy_match

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover
    sd = None


def is_audio_available() -> bool:
    return sd is not None


def list_audio_devices() -> str:
    if sd is None:
        return (
            "Audio device listing requires the sounddevice package. "
            "Install it with `pip install sounddevice`."
        )

    try:
        devices = sd.query_devices()
    except Exception as exc:
        return f"Could not list audio devices: {exc}"

    if not devices:
        return "No audio devices were found."

    lines = ["Available audio devices:"]
    for index, device in enumerate(devices):
        name = device.get("name") or "unnamed"
        inputs = device.get("max_input_channels", 0)
        outputs = device.get("max_output_channels", 0)
        default = " (default)" if index == sd.default.device else ""
        lines.append(f"{index}: {name} | in: {inputs} | out: {outputs}{default}")
    return "\n".join(lines)


def get_current_audio_device() -> str:
    if sd is None:
        return (
            "Audio device status requires the sounddevice package. "
            "Install it with `pip install sounddevice`."
        )

    try:
        devices = sd.query_devices()
        current = sd.default.device
    except Exception as exc:
        return f"Could not determine current audio device: {exc}"

    if current is None:
        return "No audio device is currently selected."

    if isinstance(current, (tuple, list)):
        current = current[1] if len(current) > 1 else current[0]

    if not isinstance(current, int) or current < 0 or current >= len(devices):
        return "The current audio device index is invalid."

    device = devices[current]
    return f"Current audio device is {current}: {device.get('name')}"


def select_audio_device(name: str) -> str:
    if sd is None:
        return (
            "Audio device selection requires the sounddevice package. "
            "Install it with `pip install sounddevice`."
        )

    try:
        devices = sd.query_devices()
    except Exception as exc:
        return f"Could not query audio devices: {exc}"

    device_names = [device.get("name") or "unnamed" for device in devices]

    def label_fn(_device, index: int) -> str:
        return device_names[index]

    match, error = resolve_fuzzy_match(name, list(devices), label_fn=label_fn)
    if error:
        return error

    index = match.index
    device = devices[index]
    try:
        sd.default.device = index
        return f"Selected audio device '{device.get('name')}'."
    except Exception as exc:
        return f"Found device but could not select it: {exc}"


def list_input_devices() -> list[tuple[int, str]]:
    """Return (index, name) pairs for devices that can capture microphone audio."""
    if sd is None:
        return []

    try:
        devices = sd.query_devices()
    except Exception:
        return []

    inputs: list[tuple[int, str]] = []
    for index, device in enumerate(devices):
        if int(device.get("max_input_channels") or 0) <= 0:
            continue
        name = device.get("name") or f"Device {index}"
        inputs.append((index, str(name)))
    return inputs


def default_input_device_index() -> Optional[int]:
    inputs = list_input_devices()
    if not inputs:
        return None
    if sd is None:
        return inputs[0][0]
    try:
        current = sd.default.device
        if isinstance(current, (tuple, list)):
            current = current[0]
        if isinstance(current, int):
            for index, _name in inputs:
                if index == current:
                    return index
    except Exception:
        pass
    return inputs[0][0]
