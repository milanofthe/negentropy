from __future__ import annotations

from pathlib import Path

from negentropy.codebase import git
from negentropy.engine import names_of, without
from negentropy.finding import Finding
from negentropy.rules import Rulebook


def of_text(book: Rulebook, subject: str, label: str, text: str, allowed: str = "") -> list[Finding]:
    lines = [line for line in text.strip().splitlines() if not line.startswith("#")]
    found = []
    for rule in book.about(subject):
        if rule.unless_subject and lines and rule.unless_subject.search(lines[0]):
            continue
        for selector in rule.selectors:
            if selector.line is None:
                continue
            read = [without(line, allowed if selector.allow else "") for line in (lines[1:] if selector.after_subject else lines)]
            hits = [line for line in read if selector.line.search(line) and not any(p.search(line) for p in selector.unless)]
            if hits:
                found.append(Finding(rule.name, label, 1, names_of(selector, "".join(hits)) if selector.names else ""))
                break
    return found


def of_history(book: Rulebook, root: Path, revisions: str, allowed: str = "") -> list[Finding]:
    log = git(root, "log", "--no-merges", "--format=%h%x01%B%x00", revisions)
    found = []
    for entry in filter(str.strip, log.split("\0")):
        short, _, message = entry.strip().partition("\x01")
        found += of_text(book, "commit", f"commit {short}", message, allowed)
    return found
