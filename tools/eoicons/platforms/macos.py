"""macOS: not implemented yet -- a Mac contributor is needed.

What is already done for you
----------------------------
``detect()`` works: it finds the .app bundle and reads out of Info.plist
everything the remaining work needs -- the current ``CFBundleIconFile`` and the
``CFBundleDocumentTypes`` array, which lists every document type the app claims
together with the ``CFBundleTypeIconFile`` each one currently uses. Run

    python tools/set-icons.py --list

on a Mac and it will print what it found.

What is left to write: plan()
-----------------------------
Return a list of :class:`Step`, each recording to ``self.journal`` before it
changes anything (see platforms/base.py and platforms/linux.py for a worked
example). The steps should be, roughly:

1. For the app icon, copy ``self.icons.macos_app_icns()`` over
   ``<bundle>/Contents/Resources/<CFBundleIconFile>.icns``. Use
   ``self.replace_file(source, target)`` -- it backs the original up and
   journals it for you, so ``--uninstall`` then works with no extra code.

   Prefer rebuilding the .icns from ``self.icons.macos_app_iconset()`` with
   ``iconutil -c icns``: icons/README.md notes the bundled .icns was built on
   Linux and is missing the 16 and 32 px 1x entries. ``iconutil`` is part of
   the Xcode command line tools, so check ``shutil.which("iconutil")`` first
   and fall back to the bundled file.

2. For each entry in ``details["document_types"]``, copy the matching
   ``self.icons.macos_filetype_icns(ext)`` over
   ``Contents/Resources/<CFBundleTypeIconFile>.icns``. The extensions a type
   claims are in ``CFBundleTypeExtensions``; pick the first one that
   ``macos_filetype_icns`` has artwork for.

   Where a document type has no ``CFBundleTypeIconFile`` at all, the Info.plist
   needs editing to add one, which is a bigger change than a file copy -- a
   ``plist`` journal kind and an ``undo()`` branch for it would be needed.

3. Make Launch Services notice. Bump the bundle's mtime and re-register it::

       touch <bundle>
       /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks\\
         /LaunchServices.framework/Versions/A/Support/lsregister -f <bundle>

   then ``killall Finder``. Rebuilding the whole Launch Services database
   (``lsregister -kill -r -domain local -domain user``) is the heavy hammer and
   resets the user's own default-app choices, so do not reach for it.

Things to watch out for
-----------------------
* The bundle is code-signed. Replacing a resource invalidates the signature, so
  Gatekeeper may refuse to launch the app afterwards. Check whether it still
  launches, and if it does not, re-sign ad hoc with ``codesign --force --deep
  --sign - <bundle>`` and say so in the output. **Verify this before setting
  ``tested = True``** -- it is the one thing that could leave a Mac user with
  an app that will not open, and unlike the Windows path there is no way to do
  this without touching the bundle.
* A bundle under /Applications needs either an admin password or for the user
  to own it. ``is_elevated()`` below reports whether we can write to it, so
  mark those steps ``needs_admin=True`` and the CLI will handle the rest.
* An application update replaces Contents/Resources, so the icons revert and
  the tool has to be re-run. Mention that in the output.
"""

from __future__ import annotations

import os
import plistlib
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import Detection, IconInstaller, Step

#: Where a Euro-Office bundle might be.
BUNDLE_DIRS = ("/Applications", "~/Applications")

#: Bundle names to look for, in order.
BUNDLE_GLOBS = ("Euro-Office*.app", "Euro Office*.app", "EuroOffice*.app")


class MacOSIconInstaller(IconInstaller):
    name = "macOS"
    tested = False

    # -- detection (works) -----------------------------------------------

    def detect(self) -> Detection:
        bundle = self._find_bundle()
        if bundle is None:
            return Detection(
                found=False,
                note="no Euro-Office application bundle found in "
                     + " or ".join(BUNDLE_DIRS),
            )
        info = self._read_info_plist(bundle)
        if info is None:
            return Detection(
                found=False,
                install_dir=bundle,
                note="found " + str(bundle) + " but could not read its "
                     "Contents/Info.plist",
            )

        document_types = []
        for entry in info.get("CFBundleDocumentTypes") or []:
            document_types.append(
                {
                    "name": entry.get("CFBundleTypeName"),
                    "extensions": entry.get("CFBundleTypeExtensions") or [],
                    "icon_file": entry.get("CFBundleTypeIconFile"),
                }
            )
        return Detection(
            found=True,
            install_dir=bundle,
            details={
                "app_icon_file": info.get("CFBundleIconFile"),
                "document_types": document_types,
                "writable": os.access(bundle, os.W_OK),
            },
        )

    @staticmethod
    def _find_bundle() -> Optional[Path]:
        for directory in BUNDLE_DIRS:
            base = Path(directory).expanduser()
            if not base.is_dir():
                continue
            for pattern in BUNDLE_GLOBS:
                for match in sorted(base.glob(pattern)):
                    if (match / "Contents" / "Info.plist").is_file():
                        return match
        return None

    @staticmethod
    def _read_info_plist(bundle: Path) -> Optional[Dict[str, Any]]:
        try:
            with open(bundle / "Contents" / "Info.plist", "rb") as handle:
                return plistlib.load(handle)
        except (OSError, plistlib.InvalidFileException):
            return None

    # -- planning (to be written) ----------------------------------------

    def plan(self, detection: Detection) -> List[Step]:
        raise NotImplementedError(
            "The macOS installer has not been written yet -- only detection.\n"
            "`--list` already shows the bundle, its CFBundleIconFile and every\n"
            "document type it claims. The module docstring in\n"
            "tools/eoicons/platforms/macos.py sets out the remaining steps.\n"
            "Patches very welcome."
        )

    def undo(self, entry: Dict[str, Any]) -> bool:
        return self.undo_shared(entry)

    def is_elevated(self) -> bool:
        return os.geteuid() == 0
