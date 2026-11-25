"""Windows: file-type icons via per-user ProgID overrides, app icon via app.ico.

How Windows picks the icon for a file
-------------------------------------
``.docx`` -> a ProgID -> that ProgID's ``DefaultIcon``. The ProgID is resolved
in this order, first hit wins::

    HKCU\\...\\Explorer\\FileExts\\.docx\\UserChoice   (the user default app)
    HKCU\\Software\\Classes\\.docx
    HKLM\\Software\\Classes\\.docx

Euro-Office ships its icons as resources *inside* ``DesktopEditors.exe`` and
registers e.g. ``DesktopEditors.exe,7``. Rather than patch a signed binary, we
write ``HKCU\\Software\\Classes\\<ProgID>\\DefaultIcon`` pointing at our own
.ico files. HKCU shadows HKLM, so this needs no administrator rights, survives
an application update, and is removed cleanly by ``--uninstall``.

The application icon is different: the Start Menu shortcut already points at
``<install>\\app.ico``, so replacing that file is enough and still touches no
binary. That does need administrator rights, because it lives in Program Files.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .base import Detection, IconInstaller, Step

# ProgID namespaces used by Euro-Office and by the ONLYOFFICE builds it is
# derived from. Rebrands keep the suffix and change the prefix, so matching on
# the suffix is what makes this portable between them.
PROGID_PREFIXES: Tuple[str, ...] = ("EuroOffice.", "ASC.")

# ProgID suffix -> the extension whose artwork it should use.
PROGID_SUFFIX_TO_EXT: Dict[str, str] = {
    # Documents
    "Document.12": "docx", "Dotx": "dotx", "Docxf": "docxf", "Oform": "oform",
    "Document.1": "doc", "Dot": "dot", "Document.2": "odt", "Ott": "ott",
    "Fodt": "fodt", "Rtf": "rtf", "Hwp": "hwp", "Hwpx": "hwpx", "Pages": "pages",
    # Spreadsheets
    "Sheet.12": "xlsx", "Xlsm": "xlsm", "Xltx": "xltx", "Xlsb": "xlsb",
    "Sheet.1": "xls", "Xlt": "xlt", "Sheet.2": "ods", "Ots": "ots",
    "Fods": "fods", "Csv": "csv", "Numbers": "numbers",
    # Presentations
    "Show.12": "pptx", "Pptm": "pptm", "SlideShow.12": "ppsx", "Potx": "potx",
    "Show.1": "ppt", "SlideShow.1": "pps", "Pot": "pot",
    "Show.2": "odp", "Otp": "otp", "Key": "key",
    # Fixed layout
    "Pdf": "pdf", "Xps": "xps", "Oxps": "oxps", "DjVu": "djvu",
    # Diagrams
    "Vsdx": "vsdx", "Odg": "odg",
    # Text and web
    "Txt": "txt", "Md": "md", "Xml": "xml", "Html": "html", "Htm": "htm",
    "Mht": "mht", "Mhtml": "mht",
    # E-books
    "Epub": "epub", "Fb2": "fb2",
}

# Suffixes that identify the application itself rather than a document type.
APP_PROGID_SUFFIXES = frozenset({"Editors"})

# Start Menu shortcuts whose icon comes from an .exe resource index rather than
# from app.ico: shortcut file name -> extension whose artwork fits it.
# "Uninstall" is deliberately absent; the set has no artwork for it.
SHORTCUT_ICON_BY_NAME: Dict[str, str] = {
    "new document": "docx",
    "new spreadsheet": "xlsx",
    "new presentation": "pptx",
    "new pdf": "pdf",
}

HIVES = ((winreg.HKEY_CURRENT_USER, "HKCU"), (winreg.HKEY_LOCAL_MACHINE, "HKLM"))
HIVE_BY_NAME = {
    "HKCU": winreg.HKEY_CURRENT_USER,
    "HKLM": winreg.HKEY_LOCAL_MACHINE,
}

SHCNE_ASSOCCHANGED = 0x08000000
SHCNF_IDLIST = 0x0000

ASSOCF_NONE = 0
ASSOCSTR_DEFAULTICON = 15

#: What the shell hands back when no application supplies an icon at all.
GENERIC_ICON = "shell32.dll,0"


def _normalise_icon(value: str) -> str:
    """Make two DefaultIcon strings comparable."""
    return str(value).strip().strip('"').lower()


def _resolved_default_icon(ext: str) -> Optional[str]:
    """The icon the shell actually resolves for ``.ext``, or None.

    Reading the registry only shows what we wrote. This runs the shell's own
    association resolution, so it is the honest answer to "will the user see
    this change?" -- and it catches extensions nominated by a stale UserChoice
    that Windows quietly ignores.
    """
    try:
        query = ctypes.windll.shlwapi.AssocQueryStringW
    except (AttributeError, OSError):
        return None
    query.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
        wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD),
    ]
    query.restype = ctypes.c_long
    size = wintypes.DWORD(1024)
    buffer = ctypes.create_unicode_buffer(size.value)
    result = query(
        ASSOCF_NONE, ASSOCSTR_DEFAULTICON, "." + ext, None, buffer,
        ctypes.byref(size),
    )
    return buffer.value or None if result == 0 else None


# ---------------------------------------------------------------------------
# small registry helpers
# ---------------------------------------------------------------------------


def _read_default(hive: int, path: str) -> Optional[str]:
    try:
        with winreg.OpenKey(hive, path) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value if isinstance(value, str) else None
    except OSError:
        return None


def _read_value(hive: int, path: str, name: str) -> Optional[str]:
    try:
        with winreg.OpenKey(hive, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value if isinstance(value, str) else None
    except OSError:
        return None


def _key_exists(hive: int, path: str) -> bool:
    try:
        winreg.CloseKey(winreg.OpenKey(hive, path))
        return True
    except OSError:
        return False


def _subkey_count(hive: int, path: str) -> int:
    try:
        with winreg.OpenKey(hive, path) as key:
            return winreg.QueryInfoKey(key)[0]
    except OSError:
        return 0


def _enum_subkeys(hive: int, path: str) -> Iterable[str]:
    try:
        key = winreg.OpenKey(hive, path)
    except OSError:
        return
    with key:
        index = 0
        while True:
            try:
                yield winreg.EnumKey(key, index)
            except OSError:
                return
            index += 1


def _exe_from_command(command: Optional[str]) -> Optional[Path]:
    """Pull the executable out of a shell open command string."""
    if not command:
        return None
    command = command.strip()
    if command.startswith('"'):
        end = command.find('"', 1)
        if end == -1:
            return None
        return Path(command[1:end])
    return Path(command.split(" ", 1)[0])


def _powershell(script: str) -> str:
    """Run a short PowerShell snippet and return stdout.

    Used only for .lnk files: editing a shortcut needs the WScript.Shell COM
    object, and shelling out keeps this module free of pywin32.
    """
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass", "-Command", script,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "powershell failed")
    return result.stdout.strip()


def _ps_literal(value: str) -> str:
    """Quote a value for a PowerShell single-quoted string."""
    return "'" + str(value).replace("'", "''") + "'"


def _lnk_icon(path: Path) -> str:
    return _powershell(
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut(" + _ps_literal(str(path)) + ");"
        "Write-Output $l.IconLocation"
    )


def _set_lnk_icon(path: Path, icon: str) -> None:
    _powershell(
        "$s=New-Object -ComObject WScript.Shell;"
        "$l=$s.CreateShortcut(" + _ps_literal(str(path)) + ");"
        "$l.IconLocation=" + _ps_literal(icon) + ";"
        "$l.Save()"
    )


# ---------------------------------------------------------------------------


class WindowsIconInstaller(IconInstaller):
    name = "Windows"
    tested = True

    @property
    def icon_store(self) -> Path:
        """Where the .ico files the registry points at are kept."""
        return self.journal.path.parent / "icons"

    # -- detection -------------------------------------------------------

    def detect(self) -> Detection:
        install_dir = self._find_install_dir()
        if install_dir is None:
            return Detection(
                found=False,
                note="no Euro-Office installation found. Looked at the "
                     "registered ProgIDs, the uninstall entries and "
                     "Program Files.",
            )

        effective = self._effective_progids()
        progids = self._find_progids(install_dir, effective)
        if not progids:
            return Detection(
                found=False,
                install_dir=install_dir,
                note="found " + str(install_dir) + " but none of its file-type "
                     "ProgIDs are registered, so there is nothing to re-icon.",
            )
        return Detection(
            found=True,
            install_dir=install_dir,
            details={
                "progids": progids,
                "effective": effective,
                "coverage": self._coverage(install_dir, progids),
            },
        )

    def _coverage(
        self, install_dir: Path, progids: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Which extensions we can actually change the icon of, and which not.

        A ProgID override only shows up if the shell resolves that ProgID for
        the extension. Plenty of types here are claimed by another application,
        or nominated by a stale UserChoice that Windows ignores, and no amount
        of re-pointing Euro-Office's ProgIDs will change what is drawn.

        An extension counts as ours when the icon the shell resolves is the
        value one of the ProgIDs we manage currently holds. Comparing values
        rather than guessing from the path matters: a previous run of a tool
        like this one may have left a ProgID pointing at a directory that is
        neither the install nor our own store.
        """
        store = str(self.icon_store).lower()
        managed = set()
        for entry in progids:
            for hive, _ in HIVES:  # HKCU first: it is what the shell merges over
                value = _read_default(
                    hive,
                    "Software\\Classes\\" + entry["progid"] + "\\DefaultIcon",
                )
                if value:
                    managed.add(_normalise_icon(value))
                    break

        install = str(install_dir).lower()
        ours: List[str] = []
        will_change: List[str] = []
        generic: List[str] = []
        other: Dict[str, str] = {}

        for ext in sorted(self.icons.filetypes):
            resolved = _resolved_default_icon(ext)
            key = _normalise_icon(resolved) if resolved else ""
            if not key or key.replace("c:\\windows\\system32\\", "") == GENERIC_ICON:
                generic.append(ext)
            elif key.startswith(store):
                ours.append(ext)
            elif key in managed or key.startswith(install):
                will_change.append(ext)
            else:
                other[ext] = resolved or ""
        return {
            "already_ours": ours,
            "will_change": will_change,
            "generic": generic,
            "other": other,
        }

    def _find_install_dir(self) -> Optional[Path]:
        # 1. The application's own ProgID knows where it lives.
        for prefix in PROGID_PREFIXES:
            for suffix in APP_PROGID_SUFFIXES:
                for hive, _ in HIVES:
                    path = "SOFTWARE\\Classes\\" + prefix + suffix
                    exe = _exe_from_command(
                        _read_default(hive, path + "\\shell\\open\\command")
                    )
                    if exe and exe.is_file():
                        return exe.parent

        # 2. Any document ProgID in the family will do just as well.
        for hive, _ in HIVES:
            for name in _enum_subkeys(hive, "SOFTWARE\\Classes"):
                if not name.startswith(PROGID_PREFIXES):
                    continue
                exe = _exe_from_command(
                    _read_default(
                        hive,
                        "SOFTWARE\\Classes\\" + name + "\\shell\\open\\command",
                    )
                )
                if exe and exe.is_file():
                    return exe.parent

        # 3. Uninstall entries.
        uninstall_roots = (
            (winreg.HKEY_LOCAL_MACHINE,
             "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE,
             "SOFTWARE\\WOW6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
            (winreg.HKEY_CURRENT_USER,
             "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall"),
        )
        for root, path in uninstall_roots:
            for name in _enum_subkeys(root, path):
                key_path = path + "\\" + name
                display = _read_value(root, key_path, "DisplayName") or ""
                if "euro-office" not in display.lower().replace(" ", "-"):
                    continue
                location = _read_value(root, key_path, "InstallLocation")
                if not location:
                    continue
                base = Path(location)
                for candidate in (base, base / "DesktopEditors"):
                    if (candidate / "DesktopEditors.exe").is_file():
                        return candidate

        # 4. Last resort: the conventional path.
        for base_dir in (
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ):
            if not base_dir:
                continue
            candidate = Path(base_dir) / "Euro-Office" / "DesktopEditors"
            if (candidate / "DesktopEditors.exe").is_file():
                return candidate
        return None

    def _find_progids(
        self, install_dir: Path, effective: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Every ProgID in the family whose icon we should replace.

        Two kinds qualify:

        * its open command runs an executable inside *install_dir* -- plainly
          Euro-Office's own;
        * it has no open command anywhere but is the effective handler for one
          of our extensions -- an icon-only stub, usually left behind when a
          sibling rebrand was uninstalled. These still decide what the user
          sees, so they have to be re-pointed as well.
        """
        install_dir = install_dir.resolve()
        winners = set(effective.values())
        found: Dict[str, Dict[str, Any]] = {}
        unknown: List[str] = []

        for hive, hive_name in HIVES:
            for name in _enum_subkeys(hive, "SOFTWARE\\Classes"):
                if not name.startswith(PROGID_PREFIXES):
                    continue
                suffix = name.split(".", 1)[1]
                if suffix in APP_PROGID_SUFFIXES:
                    continue

                command = None
                for other_hive, _ in HIVES:
                    command = command or _read_default(
                        other_hive,
                        "SOFTWARE\\Classes\\" + name + "\\shell\\open\\command",
                    )
                exe = _exe_from_command(command)

                if exe is not None:
                    try:
                        owned = exe.resolve().parent == install_dir
                    except OSError:
                        owned = False
                    reason = "registered by Euro-Office"
                elif name in winners:
                    # An icon-only stub, usually left behind by a sibling
                    # rebrand that has since been uninstalled. It has no open
                    # command, yet it is what Windows asks for the icon, so it
                    # has to be re-pointed or nothing visibly changes.
                    owned = True
                    reason = "orphaned icon stub that still wins for its type"
                elif _key_exists(
                    hive, "SOFTWARE\\Classes\\" + name + "\\DefaultIcon"
                ):
                    # Same thing, but not currently the default for any
                    # extension. Harmless today; it would serve a stale icon
                    # from a long-deleted directory the moment the user changed
                    # a default app, so bring it along.
                    owned = True
                    reason = "icon-only stub, not currently used by any type"
                else:
                    owned = False
                    reason = "not associated with this installation"

                if not owned:
                    if self.verbose:
                        print("  skipping " + name + " (" + hive_name + "): " + reason)
                    continue

                ext = PROGID_SUFFIX_TO_EXT.get(suffix)
                if ext is None:
                    unknown.append(name)
                    continue

                entry = found.setdefault(
                    name,
                    {"progid": name, "ext": ext, "hives": [], "reason": reason},
                )
                entry["hives"].append(hive_name)

        for name in sorted(set(unknown)):
            print(
                "  ! " + name + ": unknown ProgID, no artwork chosen. Add its "
                "suffix to PROGID_SUFFIX_TO_EXT in platforms/windows.py.",
                file=sys.stderr,
            )
        return [found[k] for k in sorted(found)]

    def _effective_progids(self) -> Dict[str, str]:
        """extension -> the ProgID Windows actually uses for it."""
        wanted = sorted(
            set(self.icons.filetypes) | set(PROGID_SUFFIX_TO_EXT.values())
        )
        result: Dict[str, str] = {}
        for ext in wanted:
            user_choice = (
                "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Explorer"
                "\\FileExts\\." + ext + "\\UserChoice"
            )
            progid = _read_value(winreg.HKEY_CURRENT_USER, user_choice, "ProgId")
            if not progid:
                progid = _read_default(
                    winreg.HKEY_CURRENT_USER, "SOFTWARE\\Classes\\." + ext
                ) or _read_default(
                    winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\\Classes\\." + ext
                )
            if progid:
                result[ext] = progid
        return result

    # -- planning --------------------------------------------------------

    def plan(self, detection: Detection) -> List[Step]:
        install_dir = detection.install_dir
        assert install_dir is not None
        progids: List[Dict[str, Any]] = detection.details["progids"]
        coverage: Dict[str, Any] = detection.details["coverage"]

        # Extensions whose icon the user will actually see change, as the shell
        # itself reports -- not merely those a UserChoice nominates.
        visible = set(coverage["will_change"]) | set(coverage["already_ours"])

        steps: List[Step] = []
        needed = sorted({entry["ext"] for entry in progids})
        distinct = {self.icons.resolve_ext(ext) for ext in needed}
        steps.append(
            Step(
                summary="copy " + str(len(distinct)) + " .ico files to "
                        + str(self.icon_store),
                run=lambda: self._copy_icons(needed),
            )
        )

        for entry in progids:
            progid, ext = entry["progid"], entry["ext"]
            artwork = self.icons.resolve_ext(ext)
            label = artwork + ".ico"
            if artwork != ext:
                label += " (shared with ." + ext + ")"
            if ext not in visible:
                label += "   [not the current default for its type]"
            steps.append(
                Step(
                    summary="HKCU\\Software\\Classes\\" + progid
                            + "\\DefaultIcon -> " + label,
                    run=(lambda p=progid, e=ext: self._set_default_icon(p, e)),
                )
            )

        elevated = self.is_elevated()

        # Explorer's "New ->" submenu icons.
        for shellnew in self._shellnew_icons(progids):
            hive_name, path, ext = shellnew["hive"], shellnew["path"], shellnew["ext"]
            per_user = hive_name == "HKCU"
            steps.append(
                Step(
                    summary="New-menu icon for ." + ext + " -> "
                            + self.icons.resolve_ext(ext) + ".ico  (" + hive_name + ")",
                    needs_admin=not per_user,
                    blocked=(
                        None if (elevated or per_user) else "needs an elevated prompt"
                    ),
                    run=(
                        lambda h=hive_name, p=path, e=ext: self._set_shellnew_icon(h, p, e)
                    ),
                )
            )

        app_ico = install_dir / "app.ico"
        steps.append(
            Step(
                summary="replace " + str(app_ico) + " with windows/app/euro-office.ico",
                needs_admin=True,
                blocked=None if elevated else "needs an elevated prompt",
                run=lambda: self.replace_file(self.icons.windows_app_icon(), app_ico),
            )
        )

        home = str(Path.home())
        for lnk, ext in self._shortcuts():
            per_user = str(lnk).startswith(home)
            steps.append(
                Step(
                    summary="point " + lnk.name + " at " + ext + ".ico",
                    needs_admin=not per_user,
                    blocked=(
                        None if (elevated or per_user) else "needs an elevated prompt"
                    ),
                    run=(lambda p=lnk, e=ext: self._set_shortcut_icon(p, e)),
                )
            )
        return steps

    def _shellnew_icons(self, progids: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """``IconPath`` values under ``.ext\\<ProgID>\\ShellNew``.

        These draw the entries on Explorer's right-click *New* submenu ("New ->
        Euro-Office Document"). They are a separate value from the ProgID's
        DefaultIcon and are easy to miss -- an installer that writes one leaves
        a reference to wherever its icons lived, which then rots.
        """
        managed = {entry["progid"]: entry["ext"] for entry in progids}
        found: List[Dict[str, Any]] = []
        seen = set()
        for ext in sorted(self.icons.filetypes):
            base = "Software\\Classes\\." + ext
            for hive, hive_name in HIVES:
                for progid in _enum_subkeys(hive, base):
                    if progid not in managed:
                        continue
                    path = base + "\\" + progid + "\\ShellNew"
                    current = _read_value(hive, path, "IconPath")
                    if current is None or (hive_name, path) in seen:
                        continue
                    seen.add((hive_name, path))
                    found.append(
                        {
                            "hive": hive_name,
                            "path": path,
                            "ext": ext,
                            "current": current,
                        }
                    )
        return found

    def _set_shellnew_icon(self, hive_name: str, path: str, ext: str) -> None:
        icon = self._icon_path(ext)
        if self.journal.prior("regvalue", path, "IconPath") is None:
            self.journal.record(
                "regvalue",
                hive=hive_name,
                path=path,
                name="IconPath",
                old=_read_value(HIVE_BY_NAME[hive_name], path, "IconPath"),
                created_keys=[],
            )
        if self.journal.dry_run:
            return
        with winreg.OpenKey(
            HIVE_BY_NAME[hive_name], path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "IconPath", 0, winreg.REG_SZ, str(icon))

    def _shortcuts(self) -> List[Tuple[Path, str]]:
        """The Euro-Office shortcuts whose icon comes from an .exe resource."""
        roots = [
            Path(os.environ.get("ProgramData", "C:\\ProgramData"))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("APPDATA", "."))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            Path(os.environ.get("PUBLIC", ".")) / "Desktop",
            Path.home() / "Desktop",
        ]
        out: List[Tuple[Path, str]] = []
        seen = set()
        for root in roots:
            for base in (root / "Euro-Office", root):
                if not base.is_dir():
                    continue
                for lnk in sorted(base.glob("*.lnk")):
                    ext = SHORTCUT_ICON_BY_NAME.get(lnk.stem.lower())
                    if ext and str(lnk) not in seen:
                        seen.add(str(lnk))
                        out.append((lnk, ext))
                if base.name == "Euro-Office":
                    break
        return out

    # -- actions ---------------------------------------------------------

    def _copy_icons(self, exts: Iterable[str]) -> None:
        missing: List[str] = []
        if not self.journal.dry_run:
            self.icon_store.mkdir(parents=True, exist_ok=True)
        for ext in exts:
            source = self.icons.windows_filetype_icon(ext)
            if source is None:
                missing.append(ext)
                continue
            if not self.journal.dry_run:
                shutil.copy2(source, self._icon_path(ext))
        if missing:
            print(
                "  ! no artwork for: " + ", ".join(missing)
                + " -- those types keep their old icon",
                file=sys.stderr,
            )

    def _icon_path(self, ext: str) -> Path:
        return self.icon_store / (self.icons.resolve_ext(ext) + ".ico")

    def _set_default_icon(self, progid: str, ext: str) -> None:
        icon = self._icon_path(ext)
        if "," in str(icon):
            raise RuntimeError(
                str(icon) + " contains a comma, which Windows reads as a "
                "resource index. Choose another location with --state-dir."
            )
        if not icon.exists():
            if self.journal.dry_run:
                return
            raise RuntimeError("no artwork at " + str(icon) + "; skipped " + progid)

        base = "Software\\Classes\\" + progid
        default_icon = base + "\\DefaultIcon"
        if self.journal.prior("regvalue", default_icon) is None:
            created = [
                level
                for level in (base, default_icon)
                if not _key_exists(winreg.HKEY_CURRENT_USER, level)
            ]
            self.journal.record(
                "regvalue",
                hive="HKCU",
                path=default_icon,
                name="",
                old=_read_default(winreg.HKEY_CURRENT_USER, default_icon),
                created_keys=created,
            )
        if self.journal.dry_run:
            return
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, default_icon, 0, winreg.KEY_WRITE
        ) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(icon))

    def _set_shortcut_icon(self, lnk: Path, ext: str) -> None:
        icon = self._icon_path(ext)
        if self.journal.prior("lnk", str(lnk)) is None:
            self.journal.record("lnk", path=str(lnk), old=_lnk_icon(lnk))
        if self.journal.dry_run:
            return
        _set_lnk_icon(lnk, str(icon) + ",0")

    # -- rollback --------------------------------------------------------

    def undo(self, entry: Dict[str, Any]) -> bool:
        kind = entry.get("kind")
        if kind == "regvalue":
            self._undo_regvalue(entry)
            return True
        if kind == "lnk":
            _set_lnk_icon(Path(entry["path"]), entry.get("old") or "")
            return True
        return False

    def _undo_regvalue(self, entry: Dict[str, Any]) -> None:
        path = entry["path"]
        old = entry.get("old")
        name = entry.get("name") or ""
        hive = HIVE_BY_NAME.get(entry.get("hive") or "HKCU", winreg.HKEY_CURRENT_USER)

        if old is not None:
            with winreg.CreateKeyEx(hive, path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, old)
            return

        created = entry.get("created_keys") or []
        if not created:
            # The key was already there and we added a value to it: take just
            # the value back out and leave the key alone.
            try:
                with winreg.OpenKey(hive, path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
            except OSError:
                pass
            return
        # We created the keys. Remove them deepest first, and never one that
        # has since gained subkeys of its own.
        for level in sorted(created, key=len, reverse=True):
            if _subkey_count(hive, level):
                continue
            try:
                winreg.DeleteKey(hive, level)
            except OSError:
                pass

    # -- platform bits ---------------------------------------------------

    def is_elevated(self) -> bool:
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def finish(self, ran_any: bool) -> None:
        if not ran_any:
            return
        try:
            ctypes.windll.shell32.SHChangeNotify(
                SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None
            )
        except Exception:
            pass
        print(
            "\nTold Explorer the associations changed. If a stale icon lingers:"
            "\n  ie4uinit.exe -show\nor sign out and back in."
        )
