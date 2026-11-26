from __future__ import annotations

import argparse
import sys
from pathlib import Path

from negentropy import checks
from negentropy.checks import commits
from negentropy.codebase import Codebase, root_of
from negentropy.config import Config
from negentropy.finding import ToolError
from negentropy.report import render


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="negentropy", description="Checks the whole codebase and lists what to fix.")
    commands = top.add_subparsers(dest="command")
    commands.add_parser("check", help="check the codebase of the current repository (the default)")
    message = commands.add_parser("message", help="check a commit message in a file")
    message.add_argument("file", type=Path)
    history = commands.add_parser("commits", help="check the commit messages of a revision range")
    history.add_argument("revisions")
    history.add_argument("--title", default="", help="the title of the pull request")
    history.add_argument("--description", default="", help="the description of the pull request")
    return top


def run(args: argparse.Namespace) -> list:
    root = root_of(Path.cwd())
    if args.command in (None, "check"):
        return checks.codebase_findings(Codebase(root))
    config = Config.load(root)
    named = {check.name for check in checks.active(config.off)}
    if args.command == "message":
        found = commits.message_findings("commit message", args.file.read_text(encoding="utf-8"), config.characters)
    else:
        found = commits.commit_findings(root, args.revisions, config.characters)
        found += commits.description_findings("pull request title", args.title, config.characters)
        found += commits.description_findings("pull request description", args.description, config.characters)
    return [finding for finding in found if finding.check in named]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        found = run(parser().parse_args(argv))
    except ToolError as error:
        print(f"negentropy: {error}", file=sys.stderr)
        return 2
    try:
        print(render(found, checks.CHECKS), flush=True)
    except BrokenPipeError:
        sys.stdout = None
    return 1 if found else 0
