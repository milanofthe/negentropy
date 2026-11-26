from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from negentropy import changes, messages
from negentropy.codebase import Codebase, changed_since, export, has_revision, root_of
from negentropy.config import Config
from negentropy.engine import Engine
from negentropy.finding import Finding, ToolError
from negentropy.report import counts, render, unresolved, with_reported
from negentropy.rules import Rulebook


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="negentropy", description="Checks the whole codebase and lists the findings.")
    commands = top.add_subparsers(dest="command")
    check = commands.add_parser("check", help="check the codebase of the current repository (the default)")
    check.add_argument(
        "--against", metavar="REVISION", help="pass if no check has more findings than at this revision"
    )
    commands.add_parser("next", help="check the codebase and list only the phase to fix next")
    history = commands.add_parser("commits", help="check the commit messages of a revision range")
    history.add_argument("revisions")
    history.add_argument("--title", default="", help="the title of the pull request")
    history.add_argument("--description", default="", help="the description of the pull request")
    changed = commands.add_parser("changes", help="list the changes since a revision that the owner reviews")
    changed.add_argument("revision")
    return top


def run(args: argparse.Namespace, root: Path, book: Rulebook, config: Config) -> list[Finding]:
    if args.command in (None, "check", "next"):
        return Engine(Codebase(root, config), book).findings()
    allowed = config.characters
    return (
        messages.of_history(book, root, args.revisions, allowed)
        + messages.of_text(book, "text", "pull request title", args.title, allowed)
        + messages.of_text(book, "text", "pull request description", args.description, allowed)
    )


def at_revision(root: Path, revision: str, book: Rulebook, config: Config) -> list[Finding]:
    if not has_revision(root, revision):
        return []
    with tempfile.TemporaryDirectory() as directory:
        files = export(root, revision, Path(directory))
        return Engine(Codebase(Path(directory), config, files), book).findings()


def compared(found: list[Finding], root: Path, revision: str, book: Rulebook, config: Config) -> tuple[str, int]:
    now, before = counts(found), counts(unresolved(at_revision(root, revision, book, config)))
    grown = {check: count for check, count in now.items() if count > before.get(check, 0)}
    if not grown:
        kept = ", ".join(f"{check} {count}" for check, count in sorted(now.items()))
        return f"negentropy: no check has more findings than at {revision} ({kept})", 0
    of_grown = [finding for finding in found if finding.check in grown]
    changed = changed_since(root, revision) if has_revision(root, revision) else set()
    in_changed = [finding for finding in of_grown if finding.path in changed]
    growth = ", ".join(f"{check} {count} ({before.get(check, 0)} at {revision})" for check, count in sorted(grown.items()))
    scope = "in the files changed since then" if in_changed else "in the codebase"
    header = (
        f"negentropy: these checks have more findings than at {revision}: {growth}. "
        f"The findings of these checks {scope} follow."
    )
    return "\n\n".join([header, render(in_changed or of_grown, book)]), 1


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        root = root_of(Path.cwd())
        config = Config.load(root)
        book = Rulebook.load(root, config)
        args = parser().parse_args(argv)
        if args.command == "changes":
            print(changes.report(root, args.revision), flush=True)
            return 0
        found = run(args, root, book, config)
    except ToolError as error:
        print(f"negentropy: {error}", file=sys.stderr)
        return 2
    against = getattr(args, "against", None)
    open_findings = unresolved(found)
    if against and open_findings:
        report, status = compared(open_findings, root, against, book, config)
    else:
        report = render(open_findings, book, next_phase_only=args.command == "next")
        status = 1 if open_findings else 0
    report = with_reported(report, found, book)
    try:
        print(report, flush=True)
    except BrokenPipeError:
        sys.stdout = None
    return status
