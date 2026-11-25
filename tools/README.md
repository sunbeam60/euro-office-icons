# set-icons.py

Installs the icon set in [`icons/`](../icons) over the one Euro-Office ships.

Python 3.8+, standard library only — nothing to install first. Windows works
today; Linux is written but untested; macOS is detection-only and needs a Mac
contributor (see [below](#adding-a-platform)).

```powershell
python tools/set-icons.py --list       # what is on this machine
python tools/set-icons.py --dry-run    # what would change
python tools/set-icons.py              # do it
python tools/set-icons.py --uninstall  # put it all back
```

Run it again after a Euro-Office update. It is idempotent, and a second run
will not forget what the system looked like before the first one.

## Windows

### File-type icons — no administrator rights needed

Windows resolves an icon as `.docx` → a ProgID → that ProgID's `DefaultIcon`.
Euro-Office ships its icons as resources *inside* `DesktopEditors.exe` and
registers them as `DesktopEditors.exe,7` and so on. Rather than patch a signed
binary, the script copies the `.ico` files to
`%LOCALAPPDATA%\euro-office-icons\icons` and writes

```
HKCU\Software\Classes\<ProgID>\DefaultIcon = <that path>
```

`HKCU` shadows `HKLM`, so this needs no administrator rights, survives an
application update, and comes out cleanly with `--uninstall`.

Three kinds of ProgID get re-pointed, and `--verbose` says which is which:

| | |
|---|---|
| registered by Euro-Office | its open command runs an executable in the install directory |
| orphaned icon stub that still wins for its type | no open command, but it is what Windows asks for the icon — usually left behind by a sibling ONLYOFFICE rebrand that has since been uninstalled, and the reason nothing appears to change if you ignore it |
| icon-only stub, not currently used | the same, but no extension currently points at it. Harmless today; it would serve a stale icon from a deleted folder the moment a default app changed, so it is brought along |

### How many icons will actually change

Fewer than the number of ProgIDs, usually far fewer, and `--list` tells you
which. Re-pointing a ProgID only shows up if the shell *resolves* that ProgID
for the extension, so the report asks the shell itself — via
`AssocQueryString(ASSOCSTR_DEFAULTICON)` — rather than trusting the registry,
and sorts every extension into one of three buckets:

- **will change** — Euro-Office (or an earlier run of this tool) supplies the
  icon today, so ours replaces it.
- **drawn by another application** — `.odt` under LibreOffice, `.pdf` under
  Acrobat, `.html` under a browser. Left alone. Making Euro-Office the default
  app for one moves it into the first bucket.
- **no application supplies an icon** — Windows draws its generic blank page.
  These have a stale file association: something nominates a handler that
  Windows then ignores, often an uninstalled application or an Office
  installation that never registered its icons. Re-pointing Euro-Office's
  ProgID does not help, because the shell never asks for it. Setting
  Euro-Office as the default app for the type (right-click a file → *Open
  with* → *Choose another app* → *Always*) repairs the association and picks
  up this set in one go.

The ProgIDs in the second and third buckets are still re-pointed, so they are
correct the moment the association changes. Steps for those are marked
`[not the current default for its type]`.

### Explorer's "New ->" submenu

A separate value again: `IconPath` under `.<ext>\<ProgID>\ShellNew` draws the
right-click *New -> Euro-Office Document* entries. An installer that writes one
leaves a reference to wherever its icons lived at the time, which then rots when
that directory goes away, so the script re-points these too. The ones in HKCU
need no administrator rights; any in HKLM are reported and skipped without
them, and are usually redundant because the HKCU value shadows them.

### Application icon — needs an elevated prompt

The Start Menu shortcut already points at `<install>\app.ico`, so replacing
that one file is enough; no binary is modified. It lives under Program Files,
so this step needs administrator rights. Without them the script reports the
step as skipped, does everything else, and prints the command to re-run:

```powershell
python tools/set-icons.py
```

The same step re-points the `New document` / `New spreadsheet` /
`New presentation` / `New PDF` shortcuts, whose icons come from `.exe` resource
indices rather than from `app.ico`. `Uninstall.lnk` is left alone — the set has
no artwork for it.

A Euro-Office update overwrites `app.ico`, so re-run after one. The original is
kept in `%LOCALAPPDATA%\euro-office-icons\backup\`.

### What this cannot change

`DesktopEditors.exe`'s own icon — the one Explorer draws on the executable, and
the one the running window and its taskbar button use — is a resource inside
the signed binary. Changing it means rewriting the PE resource section, which
breaks the code signature and is undone by every update. The script does not do
it, and the shortcut icons above are the reason it mostly does not matter.

## Rollback

Every change is appended to `%LOCALAPPDATA%\euro-office-icons\install-journal.json`
*before* it is made, together with the previous value, so an interrupted run is
still undoable. `--uninstall` replays it backwards: restoring a previous value,
deleting a registry key the script created, or copying a backed-up file back.

Recording the same target twice keeps the first entry. Without that, a second
run would note the script's own icons as the originals and `--uninstall` would
restore those instead.

If you delete the journal, nothing can be rolled back automatically.

## Known artwork substitutions

The set has no dedicated artwork for a couple of legacy template formats, so
they share their Open XML equivalent's design — which is identical anyway,
since the icons do not render the extension itself:

| Extension | Artwork used |
|---|---|
| `.dot` | `dotx.ico` |
| `.xlt` | `xltx.ico` |

These live in `ICON_ALIASES` in [`eoicons/catalog.py`](eoicons/catalog.py).
Drawing real artwork for them and dropping it into `icons/windows/filetypes/`
is enough — the alias then stops applying.

## Adding a platform

```
tools/
  set-icons.py              CLI: argument parsing, printing, rollback driver
  eoicons/
    catalog.py              where artwork lives in icons/; nothing else knows the layout
    journal.py              the undo journal
    platforms/
      base.py               the contract — read this first
      windows.py            implemented and tested
      linux.py              written, UNTESTED
      macos.py              detection only
```

A platform module is one class with three methods, described in
[`platforms/base.py`](eoicons/platforms/base.py):

- **`detect()`** — find the application, return a `Detection`. Return
  `Detection(found=False, note="why")` when it is absent; do not raise.
- **`plan(detection)`** — return a list of `Step`. Change nothing here: `plan`
  runs for `--dry-run` too. Each `Step.run` must call `journal.record(...)`
  *before* each change, and `journal.prior(...)` first so a re-run does not
  record over the original state. `self.replace_file(src, dst)` does the
  backup, the journalling and the re-run check for you.
- **`undo(entry)`** — reverse one journal entry of a kind your platform writes,
  returning True if you handled it. The shared `file` kind is handled for you.

Mark steps that need root or an administrator with `needs_admin=True` and set
`blocked="..."` when they cannot run; the CLI reports and skips them and
carries on with the rest. Keep every step independent and idempotent.

Set `tested = True` on the class once it works on real hardware — the CLI warns
the user while it is False.

Two things make a platform easy to develop against from anywhere:

```powershell
python tools/set-icons.py --platform linux --list      # run another platform's detect()
python tools/set-icons.py --platform linux --force -n  # and build its plan
```

### Linux

Written, **not yet run on a real desktop**. It copies the freedesktop hicolor
tree into `~/.local/share/icons/hicolor` (or `/usr/share` with `--system`) and
refreshes the icon cache. There is no per-extension registration to do: an icon
theme maps a MIME type onto an icon by name, so copying the tree is the whole
job. If you are on Linux, run `--dry-run` and then the real thing, and flip
`tested = True`.

Two things to check, both flagged in [`icons/README.md`](../icons/README.md):
the MIME types for `.docxf`, `.oform`, `.hwp` and `.hwpx` are guesses, and the
app icon is only found if the installed `.desktop` file says
`Icon=euro-office` — the script prints what it actually says.

### macOS

`detect()` works and `--list` already prints the bundle, its `CFBundleIconFile`
and every document type it claims with the icon file each one uses. The
remaining work is laid out step by step in the module docstring of
[`platforms/macos.py`](eoicons/platforms/macos.py).

One warning before you start: unlike Windows, there is no way to do this
without writing inside the `.app` bundle, which invalidates its code signature.
Check the app still launches afterwards, and that re-signing ad hoc fixes it if
not, before marking the platform tested.
