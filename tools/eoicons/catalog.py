"""Locating artwork inside the ``icons/`` tree.

Everything that knows how the icon repository is laid out lives here, so a
platform module never has to hardcode a path like ``icons/windows/filetypes``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

# Extensions that have no artwork of their own, mapped to the sibling whose
# artwork is correct for them. The icons do not render the extension itself, so
# a legacy template shares the design of its Open XML equivalent exactly.
ICON_ALIASES: Dict[str, str] = {
    "dot": "dotx",   # Word 97-2003 template -> same design as .dotx
    "xlt": "xltx",   # Excel 97-2003 template -> same design as .xltx
    "mhtml": "mht",
    "jpeg": "jpg",
}


class IconSetError(RuntimeError):
    pass


class IconSet:
    """The ``icons/`` directory of this repository."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not (self.root / "source" / "filetypes.json").is_file():
            raise IconSetError(
                f"{self.root} does not look like the icon set: "
                "source/filetypes.json is missing"
            )
        with open(self.root / "source" / "filetypes.json", "rb") as fh:
            self.filetypes: Dict[str, dict] = json.loads(fh.read().decode("utf-8-sig"))

    # -- generic ---------------------------------------------------------

    def resolve_ext(self, ext: str) -> str:
        """Map an extension onto the extension whose artwork it should use."""
        ext = ext.lower().lstrip(".")
        return ICON_ALIASES.get(ext, ext)

    def mime_for(self, ext: str) -> Optional[str]:
        entry = self.filetypes.get(self.resolve_ext(ext))
        return entry.get("mime") if entry else None

    # -- Windows ---------------------------------------------------------

    def windows_app_icon(self) -> Path:
        return self._require(self.root / "windows" / "app" / "euro-office.ico")

    def windows_filetype_icon(self, ext: str) -> Optional[Path]:
        path = self.root / "windows" / "filetypes" / f"{self.resolve_ext(ext)}.ico"
        return path if path.is_file() else None

    # -- macOS -----------------------------------------------------------

    def macos_app_iconset(self) -> Path:
        return self._require(self.root / "macos" / "app" / "AppIcon.iconset")

    def macos_app_icns(self) -> Path:
        return self._require(self.root / "macos" / "app" / "AppIcon.icns")

    def macos_filetype_icns(self, ext: str) -> Optional[Path]:
        path = self.root / "macos" / "filetypes" / f"{self.resolve_ext(ext)}.icns"
        return path if path.is_file() else None

    # -- Linux -----------------------------------------------------------

    def linux_hicolor(self) -> Path:
        return self._require(self.root / "linux" / "icons" / "hicolor")

    # -- helpers ---------------------------------------------------------

    @staticmethod
    def _require(path: Path) -> Path:
        if not path.exists():
            raise IconSetError(f"expected artwork is missing: {path}")
        return path


def find_icon_set(start: Optional[Path] = None) -> IconSet:
    """Walk up from *start* (default: this file) looking for an ``icons/`` tree."""
    here = Path(start or __file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "icons" / "source" / "filetypes.json").is_file():
            return IconSet(candidate / "icons")
        if (candidate / "source" / "filetypes.json").is_file():
            return IconSet(candidate)
    raise IconSetError(
        "could not find the icon set. Run this from inside the repository, or "
        "pass --icons /path/to/icons"
    )
