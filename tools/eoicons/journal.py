"""An undo journal.

Every change a platform module makes is appended here first, together with
whatever is needed to put the system back. ``--uninstall`` replays the journal
backwards. If the journal is lost, nothing can be rolled back automatically,
so platform modules should record *before* they write.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

JOURNAL_VERSION = 1


def state_dir() -> Path:
    """Per-user directory holding installed icons, backups and the journal.

    It must be somewhere stable and readable at logon: on Windows the registry
    points *at* these files, so a temporary directory would break the icons the
    moment it was cleaned up.
    """
    env = os.environ
    if os.name == "nt":
        base = Path(env.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "euro-office-icons"


class Journal:
    def __init__(self, path: Path, dry_run: bool = False):
        self.path = Path(path)
        self.dry_run = dry_run
        self.entries: List[Dict[str, Any]] = []
        self.meta: Dict[str, Any] = {}

    # -- lifecycle -------------------------------------------------------

    @classmethod
    def open_for_append(cls, path: Path, dry_run: bool = False) -> "Journal":
        """Continue an existing journal, or start a new one.

        Re-running the installer -- after an application update, say -- must not
        forget what the system looked like before the *first* run. So the
        entries already on disk are kept, and :meth:`record` will not overwrite
        one: otherwise the second run would note our own icons as the originals
        and ``--uninstall`` would restore those instead.
        """
        if Path(path).is_file():
            try:
                journal = cls.load(path)
                journal.dry_run = dry_run
                return journal
            except (OSError, ValueError, RuntimeError) as exc:
                raise RuntimeError(
                    f"{path} exists but could not be read ({exc}). Move it aside "
                    "to start fresh -- but then the changes it describes can no "
                    "longer be rolled back automatically."
                )
        return cls(path, dry_run=dry_run)

    @classmethod
    def load(cls, path: Path) -> "Journal":
        journal = cls(path)
        with open(path, "rb") as fh:
            data = json.loads(fh.read().decode("utf-8-sig"))
        if isinstance(data, list):  # tolerate a bare list
            data = {"version": JOURNAL_VERSION, "entries": data}
        if data.get("version") != JOURNAL_VERSION:
            raise RuntimeError(
                f"{path} was written by an incompatible version "
                f"({data.get('version')!r}); roll back with that version instead"
            )
        journal.entries = list(data.get("entries") or [])
        journal.meta = {k: v for k, v in data.items() if k not in ("entries",)}
        return journal

    def save(self) -> None:
        if self.dry_run:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": JOURNAL_VERSION,
            "written": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "platform": os.name,
            "entries": self.entries,
        }
        tmp = self.path.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(payload, fh, indent=2)
        os.replace(tmp, self.path)

    # -- recording -------------------------------------------------------

    @staticmethod
    def _identity(entry: Dict[str, Any]) -> tuple:
        return (entry.get("kind"), str(entry.get("path")), entry.get("name") or "")

    def prior(self, kind: str, path: Any, name: str = "") -> Optional[Dict[str, Any]]:
        """The entry already recorded for this target, if there is one.

        A caller that is about to overwrite something should check this first:
        if an entry exists, the pristine state is already safe and must not be
        recorded over.
        """
        wanted = (kind, str(path), name)
        for entry in self.entries:
            if self._identity(entry) == wanted:
                return entry
        return None

    def record(self, kind: str, **fields: Any) -> Dict[str, Any]:
        """Note one reversible change. Call this before making it.

        Recording the same target twice keeps the first entry, so the value
        restored on rollback is always the one from before we touched anything.
        """
        entry = {"kind": kind}
        entry.update(fields)
        existing = self.prior(kind, fields.get("path"), fields.get("name") or "")
        if existing is not None:
            return existing
        self.entries.append(entry)
        # Persist as we go: an interrupted run must still be undoable.
        self.save()
        return entry

    def backup_file(self, path: Path) -> Optional[str]:
        """Copy *path* aside and return the backup location, or None if absent."""
        path = Path(path)
        if not path.exists():
            return None
        backups = self.path.parent / "backup"
        target = backups / path.name
        n = 1
        while target.exists():
            target = backups / f"{path.stem}.{n}{path.suffix}"
            n += 1
        if self.dry_run:
            return str(target)
        backups.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        return str(target)

    def __len__(self) -> int:
        return len(self.entries)
