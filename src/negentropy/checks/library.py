from __future__ import annotations

from negentropy.codebase import Codebase
from negentropy.config import BINARY_PATHS, matches
from negentropy.finding import Check, Finding


def in_library(check: str, kind: str, binaries: bool):
    def find(codebase: Codebase):
        for match in codebase.syntax.of_kind(kind):
            if codebase.in_library(match) and (binaries or not matches(match.path, BINARY_PATHS)):
                yield Finding(check, match.path, match.lines[0])

    return find


def dead_code_allowances(codebase: Codebase):
    for match in codebase.syntax.of_kind("deadcode"):
        if not codebase.in_test(match):
            yield Finding("dead-code", match.path, match.lines[0])


CHECKS = [
    Check(
        "unwrap",
        "`unwrap` or `expect` in library code: a panic on a path the caller cannot handle. "
        "Return the error, or make the failing state unrepresentable in the type.",
        in_library("unwrap", "unwrap", binaries=True),
    ),
    Check(
        "print",
        "Printing in library code. A library returns values and reports through the logger its caller set up, "
        "so the caller decides what is shown.",
        in_library("print", "print", binaries=False),
    ),
    Check(
        "environment",
        "An environment variable read in library code: a switch no caller sees and no test sets. "
        "Take the value as an option of the API, and let the binary read the environment.",
        in_library("environment", "environment", binaries=False),
    ),
    Check(
        "dead-code",
        "An allowance for dead or unused code. Code that nothing uses is deleted, version control keeps it. "
        "An old path kept beside its replacement is the one the next reader copies.",
        dead_code_allowances,
    ),
]
