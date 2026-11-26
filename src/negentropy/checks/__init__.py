from __future__ import annotations

from negentropy.checks import budgets, comments, commits, duplicates, files, library, numbers, snapshots
from negentropy.codebase import Codebase
from negentropy.finding import Check, Finding, ToolError

CHECKS: list[Check] = [
    *comments.CHECKS,
    *files.CHECKS,
    *numbers.CHECKS,
    *snapshots.CHECKS,
    *library.CHECKS,
    *duplicates.CHECKS,
    *budgets.CHECKS,
    *commits.CHECKS,
]
BY_NAME = {check.name: check for check in CHECKS}


def active(off: tuple[str, ...]) -> list[Check]:
    unknown = set(off) - set(BY_NAME)
    if unknown:
        raise ToolError(f"negentropy.toml: `off` names no check: {sorted(unknown)}")
    return [check for check in CHECKS if check.name not in off]


def codebase_findings(codebase: Codebase) -> list[Finding]:
    return [
        finding
        for check in active(codebase.config.off)
        if check.find is not None
        for finding in check.find(codebase)
    ]
