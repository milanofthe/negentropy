from __future__ import annotations

import re
from pathlib import Path

from negentropy.checks.files import foreign_characters, named
from negentropy.codebase import git
from negentropy.finding import Check, Finding

TOOLS = r"(claude|anthropic|copilot|cursor|codex|chatgpt|openai|gemini|devin|aider)"
ATTRIBUTION = re.compile(rf"(?i)co-authored-by:.*\b{TOOLS}\b|generated (with|by)\b.*\b{TOOLS}\b")
REVERT_BODY = re.compile(r"^This reverts commit [0-9a-f]+\.$")


def message_findings(label: str, message: str, allowed: str = "") -> list[Finding]:
    lines = [line for line in message.strip().splitlines() if not line.startswith("#")]
    body = [line for line in lines[1:] if line.strip() and not REVERT_BODY.match(line)]
    found = []
    if body and not lines[0].startswith("Merge "):
        found.append(Finding("commit-message", label, 1))
    found += description_findings(label, "\n".join(lines), allowed)
    return found


def description_findings(label: str, text: str, allowed: str = "") -> list[Finding]:
    found = []
    if ATTRIBUTION.search(text):
        found.append(Finding("attribution", label, 1))
    if foreign := foreign_characters(text.replace("\r", "").replace("\n", ""), allowed):
        found.append(Finding("characters", label, 1, named(foreign)))
    return found


def commit_findings(root: Path, revisions: str, allowed: str = "") -> list[Finding]:
    log = git(root, "log", "--no-merges", "--format=%h%x01%B%x00", revisions)
    found = []
    for entry in filter(str.strip, log.split("\0")):
        short, _, message = entry.strip().partition("\x01")
        found += message_findings(f"commit {short}", message, allowed)
    return found


CHECKS = [
    Check(
        "commit-message",
        "A commit message with more than one line. One short line says what changed; "
        "the reasons and the details belong to the pull request or the issue.",
    ),
    Check(
        "attribution",
        "A commit or a pull request that names an AI tool as author. The person who commits is the author: "
        "remove the line.",
    ),
]
