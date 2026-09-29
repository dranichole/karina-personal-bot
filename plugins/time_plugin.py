"""Example plugin: tell the current local time."""

from __future__ import annotations

import re
from datetime import datetime


def register(registry) -> None:
    pattern = re.compile(r"^(?:what(?:'s| is) the )?time\??$|current time", re.I)

    def matcher(text: str):
        return True if pattern.search(text.strip()) else None

    def handler() -> str:
        return f"The current time is {datetime.now().strftime('%I:%M %p').lstrip('0')}."

    registry.add("time", "time                       - show the current time", matcher, handler)
