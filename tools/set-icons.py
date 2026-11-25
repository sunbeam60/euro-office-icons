#!/usr/bin/env python3
"""Replace Euro-Office's icons with the set in this repository.

    python tools/set-icons.py --list        # what is on this machine
    python tools/set-icons.py --dry-run     # what would change
    python tools/set-icons.py               # do it
    python tools/set-icons.py --uninstall   # put everything back

Stdlib only, Python 3.8+. The per-platform work lives in tools/eoicons/platforms/.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eoicons.catalog import IconSet, IconSetError, find_icon_set  # noqa: E402
from eoicons.journal import Journal, state_dir  # noqa: E402
from eoicons.platforms import current_platform, get_installer  # noqa: E402

JOURNAL_NAME = "install-journal.json"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="set-icons.py",
        description="Replace Euro-Office's file-type and application icons "
                    "with the set in this repository.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="On Windows the file-type icons need no administrator rights. "
               "Replacing the application icon does, because it lives in "
               "Program Files; without it that step is reported and skipped.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--list", action="store_true",
        help="show what was detected and exit, changing nothing",
    )
    mode.add_argument(
        "--uninstall", action="store_true",
        help="undo a previous run, using the journal it left behind",
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true",
        help="print the steps without carrying any of them out",
    )
    parser.add_argument(
        "--icons", type=Path, default=None, metavar="DIR",
        help="path to the icons/ directory (found automatically by default)",
    )
    parser.add_argument(
        "--platform", default=None, choices=("windows", "macos", "linux"),
        help="override platform detection (for inspecting another platform's plan)",
    )
    parser.add_argument(
        "--state-dir", type=Path, default=None, metavar="DIR",
        help="where installed icons, backups and the journal are kept "
             "(default: " + str(state_dir()) + ")",
    )
    parser.add_argument(
        "--system", action="store_true",
        help="Linux: install into /usr/share instead of the user's own data dir",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="install even though the application was not found (Linux only: "
             "an icon theme is just a set of names, so it can go in first)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="explain what was skipped and why",
    )
    return parser


def describe(installer, detection) -> None:
    print("Platform:   " + installer.name)
    if not installer.tested:
        print("            (this platform's module is UNTESTED -- "
              "use --dry-run first)")
    if detection.install_dir:
        print("Installed:  " + str(detection.install_dir))
    if not detection.found:
        print("\n" + (detection.note or "nothing to do."))
        return

    progids = detection.details.get("progids")
    if progids:
        print("ProgIDs:    " + str(len(progids)) + " to re-point")

    coverage = detection.details.get("coverage")
    if coverage:
        changing = sorted(coverage["will_change"])
        done = sorted(coverage["already_ours"])
        generic = sorted(coverage["generic"])
        other = coverage["other"]

        print(
            "\nWhat the shell actually draws today, per extension "
            "(not just what the registry claims):"
        )
        if changing:
            print(
                "  will change (" + str(len(changing)) + "): "
                + ", ".join("." + e for e in changing)
            )
        if done:
            print(
                "  already using this set (" + str(len(done)) + "): "
                + ", ".join("." + e for e in done)
            )
        if not changing and not done:
            print("  none -- Euro-Office does not currently supply any file icon")
        if other:
            print(
                "  drawn by another application (" + str(len(other)) + "), "
                "left alone: " + ", ".join("." + e for e in sorted(other))
            )
            if installer.verbose:
                for ext in sorted(other):
                    print("      ." + ext.ljust(7) + other[ext])
        if generic:
            print(
                "  no application supplies an icon (" + str(len(generic))
                + "), so Windows draws its generic one: "
                + ", ".join("." + e for e in generic)
            )
            print(
                "      These are not ours to fix here: the file association "
                "itself is stale.\n"
                "      Set Euro-Office as the default app for one (right-click "
                "a file ->\n"
                "      Open with -> Choose another app -> Always) and it picks "
                "up this set."
            )

    if progids and installer.verbose:
        print("\n            ProgID                     artwork  why")
        for entry in progids:
            print(
                "            " + entry["progid"].ljust(26)
                + entry["ext"].ljust(9) + entry["reason"]
            )

    document_types = detection.details.get("document_types")
    if document_types:
        print("Document types claimed by the bundle:")
        for entry in document_types:
            exts = ", ".join("." + e for e in entry["extensions"]) or "-"
            print(
                "            " + str(entry["name"] or "?").ljust(34)
                + exts.ljust(28) + "icon=" + str(entry["icon_file"] or "none")
            )
        print("App icon file: " + str(detection.details.get("app_icon_file")))


def run_steps(installer, steps: List, dry_run: bool) -> int:
    width = max((len(s.summary) for s in steps), default=0)
    done = failed = skipped = 0

    for step in steps:
        if step.blocked:
            print("  skip  " + step.summary.ljust(width) + "   " + step.blocked)
            skipped += 1
            continue
        if dry_run:
            print("  would  " + step.summary)
            done += 1
            continue
        try:
            step.run()
        except Exception as exc:  # one failed step must not stop the rest
            print("  FAIL  " + step.summary.ljust(width) + "   " + str(exc))
            if installer.verbose:
                traceback.print_exc()
            failed += 1
        else:
            print("  ok    " + step.summary)
            done += 1

    verb = "would change" if dry_run else "changed"
    summary = str(done) + " " + verb
    if skipped:
        summary += ", " + str(skipped) + " skipped"
    if failed:
        summary += ", " + str(failed) + " failed"
    print("\n" + summary + ".")

    if skipped and not dry_run:
        print(
            "\nThe skipped steps need administrator rights. Re-run from an "
            "elevated prompt:\n  " + " ".join([sys.executable, *sys.argv])
        )
    return 1 if failed else 0


def do_uninstall(installer, journal_path: Path, dry_run: bool) -> int:
    if not journal_path.is_file():
        print(
            "No journal at " + str(journal_path) + ", so there is nothing "
            "recorded to undo.",
            file=sys.stderr,
        )
        return 1
    journal = Journal.load(journal_path)
    print("Undoing " + str(len(journal)) + " change(s) from " + str(journal_path))

    failed = 0
    for entry in reversed(journal.entries):
        label = entry.get("kind", "?") + " " + str(entry.get("path"))
        if dry_run:
            print("  would restore  " + label)
            continue
        try:
            if not (installer.undo(entry) or installer.undo_shared(entry)):
                print("  skip  " + label + "   (unknown kind for this platform)")
                continue
        except Exception as exc:
            print("  FAIL  " + label + "   " + str(exc))
            failed += 1
        else:
            print("  ok    " + label)

    if not dry_run and not failed:
        spent = journal_path.with_suffix(".json.undone")
        n = 1
        while spent.exists():  # a previous rollback already claimed the name
            spent = journal_path.with_suffix(".json.undone.%d" % n)
            n += 1
        journal_path.replace(spent)
        print("\nRestored. The journal is now " + str(spent) + ".")
        installer.finish(True)
    elif failed:
        print(
            "\n" + str(failed) + " change(s) could not be undone. The journal "
            "has been kept, so you can fix the cause and run --uninstall again."
        )
    return 1 if failed else 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        icons: IconSet = IconSet(args.icons) if args.icons else find_icon_set()
    except IconSetError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2

    base = Path(args.state_dir) if args.state_dir else state_dir()
    journal_path = base / JOURNAL_NAME
    try:
        journal = Journal.open_for_append(
            journal_path, dry_run=args.dry_run or args.list
        )
    except RuntimeError as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2

    platform_key = args.platform or current_platform()
    installer_class = get_installer(platform_key)
    kwargs = {}
    if platform_key == "linux":
        kwargs["system"] = args.system
    installer = installer_class(icons, journal, verbose=args.verbose, **kwargs)

    print("Icon set:   " + str(icons.root))
    print("State dir:  " + str(base))

    if args.uninstall:
        return do_uninstall(installer, journal_path, args.dry_run)

    detection = installer.detect()
    describe(installer, detection)
    if args.list:
        return 0
    if not detection.found:
        if not (args.force and installer.can_force):
            if args.force:
                print(
                    "\n--force cannot help here: the plan needs to know where "
                    "the application is installed.",
                    file=sys.stderr,
                )
            return 1
        print("\n--force given, carrying on without the application.")

    try:
        steps = installer.plan(detection)
    except NotImplementedError as exc:
        print("\n" + str(exc), file=sys.stderr)
        return 3

    print("\n" + ("Dry run" if args.dry_run else "Applying") + ":")
    code = run_steps(installer, steps, args.dry_run)
    if not args.dry_run:
        installer.finish(True)
        print("Journal:    " + str(journal_path) + "  (--uninstall reads this)")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        sys.exit(130)
