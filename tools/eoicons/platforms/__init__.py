"""Platform module registry."""

from __future__ import annotations

import sys
from typing import Dict, Type

from .base import Detection, IconInstaller, Step

__all__ = ["Detection", "IconInstaller", "Step", "get_installer", "PLATFORMS"]

#: Key is the value :func:`current_platform` returns.
PLATFORMS: Dict[str, str] = {
    "windows": "eoicons.platforms.windows:WindowsIconInstaller",
    "macos": "eoicons.platforms.macos:MacOSIconInstaller",
    "linux": "eoicons.platforms.linux:LinuxIconInstaller",
}


def current_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def get_installer(key: str) -> Type[IconInstaller]:
    try:
        target = PLATFORMS[key]
    except KeyError:
        raise SystemExit(
            f"no icon installer for {key!r}; known: {', '.join(sorted(PLATFORMS))}"
        )
    module_name, class_name = target.split(":")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)
