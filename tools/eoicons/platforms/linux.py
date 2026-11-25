"""Linux (freedesktop): install the hicolor theme tree, then refresh the cache.

UNTESTED. The steps follow icons/README.md exactly, but nobody has run this on
a real desktop yet. If you are on Linux, run it with --dry-run first, then for
real, and set ``tested = True`` below once it works. See platforms/base.py for
what the contract expects.

Linux needs no per-extension registration: an icon theme maps a MIME type onto
an icon by name, so copying the tree is the whole job. Two things are worth
checking afterwards, both noted in icons/README.md:

* the MIME types for .docxf, .oform, .hwp and .hwpx are guesses, so those icon
  files may need renaming to match whatever shared-mime-info the app installs;
* the app icon is picked up from ``Icon=euro-office`` in the .desktop file. If
  the installed .desktop names something else, this will install artwork nobody
  looks up -- _desktop_icon_name() below reports what it actually says.
"""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Detection, IconInstaller, Step

#: Where a .desktop file for the app might live.
DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "~/.local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
)

#: Names a Euro-Office .desktop file is likely to have.
DESKTOP_GLOBS = ("*euro*office*.desktop", "*eurooffice*.desktop")


class LinuxIconInstaller(IconInstaller):
    name = "Linux"
    tested = False
    can_force = True

    def __init__(self, *args: Any, system: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.system = system

    # -- detection -------------------------------------------------------

    @property
    def theme_root(self) -> Path:
        if self.system:
            return Path("/usr/share/icons/hicolor")
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        return Path(base) / "icons" / "hicolor"

    def detect(self) -> Detection:
        desktop = self._find_desktop_file()
        if desktop is None:
            return Detection(
                found=False,
                note="no Euro-Office .desktop file found in "
                     + ", ".join(DESKTOP_DIRS)
                     + ". Install the app first, or pass --force to install the "
                       "icon theme anyway.",
            )
        return Detection(
            found=True,
            install_dir=desktop.parent,
            details={
                "desktop_file": desktop,
                "icon_name": self._desktop_icon_name(desktop),
            },
        )

    @staticmethod
    def _find_desktop_file() -> Optional[Path]:
        for directory in DESKTOP_DIRS:
            base = Path(directory).expanduser()
            if not base.is_dir():
                continue
            for pattern in DESKTOP_GLOBS:
                for match in sorted(base.glob(pattern)):
                    return match
        return None

    @staticmethod
    def _desktop_icon_name(desktop: Path) -> Optional[str]:
        """The Icon= name the .desktop file asks the theme for."""
        try:
            for line in desktop.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Icon="):
                    return line.split("=", 1)[1].strip()
        except OSError:
            pass
        return None

    # -- planning --------------------------------------------------------

    def plan(self, detection: Detection) -> List[Step]:
        source = self.icons.linux_hicolor()
        target = self.theme_root
        needs_admin = self.system

        icon_name = detection.details.get("icon_name")
        if icon_name and icon_name != "euro-office":
            print(
                "  ! the .desktop file asks for Icon=" + icon_name + ", but the "
                "icon set installs 'euro-office'. Either change the .desktop "
                "file or rename apps/euro-office.* in the theme tree.",
                file=sys.stderr,
            )

        files = [p for p in source.rglob("*") if p.is_file()]
        steps: List[Step] = [
            Step(
                summary="install " + str(len(files)) + " theme files into " + str(target),
                needs_admin=needs_admin,
                blocked=None if self._can_write(target) else "cannot write " + str(target),
                run=lambda: self._install_tree(source, target),
            )
        ]
        for command, label in (
            (["gtk-update-icon-cache", "-f", "-t", str(target)], "refresh the GTK icon cache"),
            (["update-desktop-database"], "refresh the desktop database"),
        ):
            if shutil.which(command[0]):
                steps.append(
                    Step(
                        summary=label + " (" + command[0] + ")",
                        needs_admin=needs_admin,
                        run=(lambda c=command: self._run(c)),
                    )
                )
        return steps

    def _can_write(self, target: Path) -> bool:
        probe = target
        while not probe.exists() and probe != probe.parent:
            probe = probe.parent
        return os.access(probe, os.W_OK)

    def _install_tree(self, source: Path, target: Path) -> None:
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            destination = target / path.relative_to(source)
            if destination.exists() and filecmp.cmp(path, destination, shallow=False):
                continue
            if self.journal.prior("file", str(destination)) is None:
                self.journal.record(
                    "file",
                    path=str(destination),
                    backup=self.journal.backup_file(destination),
                    existed=destination.exists(),
                )
            if self.journal.dry_run:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)

    def _run(self, command: List[str]) -> None:
        if self.journal.dry_run:
            return
        subprocess.run(command, check=False)

    # -- rollback --------------------------------------------------------

    def undo(self, entry: Dict[str, Any]) -> bool:
        return self.undo_shared(entry)

    def is_elevated(self) -> bool:
        return os.geteuid() == 0

    def finish(self, ran_any: bool) -> None:
        if ran_any:
            print(
                "\nIf icons look unchanged, log out and back in: some desktops "
                "cache the theme for the life of the session."
            )
