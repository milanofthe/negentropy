from __future__ import annotations

import argparse
import sys
from pathlib import Path

from negentropy import messages
from negentropy.codebase import Codebase, root_of
from negentropy.config import Config
from negentropy.engine import Engine
from negentropy.finding import Finding, ToolError
from negentropy.report import render
from negentropy.rules import Rulebook


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(prog="negentropy", description="Checks the whole codebase and lists the findings.")
    commands = top.add_subparsers(dest="command")
    commands.add_parser("check", help="check the codebase of the current repository (the default)")
    message = commands.add_parser("message", help="check a commit message in a file")
    message.add_argument("file", type=Path)
    history = commands.add_parser("commits", help="check the commit messages of a revision range")
    history.add_argument("revisions")
    history.add_argument("--title", default="", help="the title of the pull request")
    history.add_argument("--description", default="", help="the description of the pull request")
    return top


def run(args: argparse.Namespace, root: Path, book: Rulebook, config: Config) -> list[Finding]:
    if args.command in (None, "check"):
        return Engine(Codebase(root, config), book).findings()
    allowed = config.characters
    if args.command == "message":
        return messages.of_text(book, "commit", "commit message", args.file.read_text(encoding="utf-8"), allowed)
    return (
        messages.of_history(book, root, args.revisions, allowed)
        + messages.of_text(book, "text", "pull request title", args.title, allowed)
        + messages.of_text(book, "text", "pull request description", args.description, allowed)
    )


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    try:
        root = root_of(Path.cwd())
        config = Config.load(root)
        book = Rulebook.load(root, config)
        found = run(parser().parse_args(argv), root, book, config)
    except ToolError as error:
        print(f"negentropy: {error}", file=sys.stderr)
        return 2
    try:
        print(render(found, book.rules), flush=True)
    except BrokenPipeError:
        sys.stdout = None
    return 1 if found else 0
