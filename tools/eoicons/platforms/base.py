"""The contract a platform module implements.

To add support for a platform, create ``eoicons/platforms/<name>.py`` with a
subclass of :class:`IconInstaller` and register it in
``eoicons/platforms/__init__.py``. You need to provide three things:

``detect()``
    Find the installed application. Return a :class:`Detection`. If it is not
    installed, return ``Detection(found=False, note="why")`` -- do not raise.

``plan(detection, journal)``
    Return a list of :class:`Step`. Do not change anything here: ``plan`` runs
    for ``--dry-run`` too. Each step's ``run`` callable does the work, and must
    call ``journal.record(...)`` *before* each change it makes.

``undo(entry)``
    Reverse one journal entry of a ``kind`` your platform writes. Return True
    if you handled it. Shared kinds (``file``) are handled for you.

Keep every step independent and idempotent: a user will re-run this after an
application update, and a step that fails should not stop the others.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from ..catalog import IconSet
from ..journal import Journal


@dataclass
class Detection:
    """What was found on this machine."""

    found: bool
    note: str = ""
    install_dir: Optional[Path] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """One reversible unit of work."""

    summary: str
    run: Callable[[], None]
    needs_admin: bool = False
    # Shown instead of running when the step cannot be performed.
    blocked: Optional[str] = None


class IconInstaller:
    #: Shown in messages, e.g. "Windows".
    name = "unknown"
    #: Set False while a platform is still being worked on; the CLI then warns.
    tested = False
    #: True where installing without the application present is still useful --
    #: a freedesktop icon theme is only a set of names, so it can go in first.
    #: False where the plan needs the install directory to exist.
    can_force = False

    def __init__(self, icons: IconSet, journal: Journal, verbose: bool = False):
        self.icons = icons
        self.journal = journal
        self.verbose = verbose

    # -- to implement ----------------------------------------------------

    def detect(self) -> Detection:
        raise NotImplementedError

    def plan(self, detection: Detection) -> List[Step]:
        raise NotImplementedError

    def undo(self, entry: Dict[str, Any]) -> bool:
        return False

    def finish(self, ran_any: bool) -> None:
        """Hook for a post-install refresh (clearing an icon cache, say)."""

    # -- shared helpers --------------------------------------------------

    def is_elevated(self) -> bool:
        """True if the process can write to system locations."""
        return True

    def replace_file(self, source: Path, target: Path) -> None:
        """Overwrite *target* with *source*, keeping a restorable backup.

        On a re-run the existing backup is left alone: it holds the original
        file, whereas a fresh one would only capture our own replacement.
        """
        if self.journal.prior("file", str(target)) is None:
            backup = self.journal.backup_file(target)
            self.journal.record(
                "file", path=str(target), backup=backup, existed=target.exists()
            )
        if self.journal.dry_run:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    def undo_shared(self, entry: Dict[str, Any]) -> bool:
        if entry.get("kind") != "file":
            return False
        target = Path(entry["path"])
        backup = entry.get("backup")
        if backup and Path(backup).exists():
            shutil.copy2(backup, target)
        elif not entry.get("existed", True) and target.exists():
            target.unlink()
        return True
