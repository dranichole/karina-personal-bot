"""Plugin command registry. Drop a .py file in plugins/ with register(registry)."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from paths import resource_dirs

Matcher = Callable[[str], Any]
Handler = Callable[..., str]


@dataclass
class RegisteredCommand:
    name: str
    help_text: str
    matcher: Matcher
    handler: Handler


class CommandRegistry:
    def __init__(self) -> None:
        self.commands: list[RegisteredCommand] = []

    def add(self, name: str, help_text: str, matcher: Matcher, handler: Handler) -> None:
        self.commands.append(
            RegisteredCommand(name=name, help_text=help_text, matcher=matcher, handler=handler)
        )

    def try_handle(self, text: str) -> Optional[str]:
        for command in self.commands:
            matched = command.matcher(text)
            if matched is None:
                continue
            if matched is True:
                return command.handler()
            if isinstance(matched, tuple):
                return command.handler(*matched)
            return command.handler(matched)
        return None

    def help_lines(self) -> list[str]:
        return [f"  {command.help_text}" for command in self.commands]


_registry: Optional[CommandRegistry] = None


def get_registry() -> CommandRegistry:
    global _registry
    if _registry is None:
        _registry = CommandRegistry()
        load_plugins(_registry)
    return _registry


def load_plugins(registry: CommandRegistry) -> None:
    seen: set[Path] = set()
    for folder in resource_dirs():
        plugin_dir = folder / "plugins"
        if not plugin_dir.is_dir():
            continue
        for path in sorted(plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            _load_plugin_file(resolved, registry)


def _load_plugin_file(path: Path, registry: CommandRegistry) -> None:
    module_name = f"karina_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        register = getattr(module, "register", None)
        if callable(register):
            register(registry)
    except Exception:
        pass
