"""Karina camera helpers for webcam snapshots."""

from __future__ import annotations

import os
from pathlib import Path

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


def is_camera_available() -> bool:
    return cv2 is not None


def snapshot_file_path() -> str:
    folder = Path.cwd()
    return str(folder / "karina_snapshot.png")


def take_snapshot() -> str:
    if cv2 is None:
        return (
            "Camera support requires OpenCV. Install it with `pip install opencv-python` "
            "and restart Karina."
        )

    capture = cv2.VideoCapture(0)
    if not capture.isOpened():
        return "Unable to access the webcam. Make sure your camera is connected and not in use."

    success, frame = capture.read()
    capture.release()
    if not success or frame is None:
        return "The webcam opened but failed to capture an image."

    path = snapshot_file_path()
    cv2.imwrite(path, frame)
    return f"Snapshot saved to {path}."