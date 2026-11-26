from __future__ import annotations

from negentropy.codebase import Codebase
from negentropy.config import BINARY_PATHS, matches
from negentropy.finding import Check, Finding


def unwraps(codebase: Codebase):
    for match in codebase.syntax.of_kind("unwrap"):
        if codebase.in_library(match):
            yield Finding("unwrap", match.path, match.lines[0])


def prints(codebase: Codebase):
    for match in codebase.syntax.of_kind("print"):
        if codebase.in_library(match) and not matches(match.path, BINARY_PATHS):
            yield Finding("print", match.path, match.lines[0])


def environment_reads(codebase: Codebase):
    for match in codebase.syntax.of_kind("environment"):
        if codebase.in_library(match) and not matches(match.path, BINARY_PATHS):
            yield Finding("environment", match.path, match.lines[0])


def dead_code_allowances(codebase: Codebase):
    for match in codebase.syntax.of_kind("deadcode"):
        if not codebase.in_test(match):
            yield Finding("dead-code", match.path, match.lines[0])


CHECKS = [
    Check(
        "unwrap",
        "`unwrap` or `expect` in library code: a panic on a path the caller cannot handle. "
        "Return the error, or make the failing state unrepresentable in the type.",
        unwraps,
    ),
    Check(
        "print",
        "Printing in library code. A library returns values and reports through the logger its caller set up, "
        "so the caller decides what is shown.",
        prints,
    ),
    Check(
        "environment",
        "An environment variable read in library code: a switch no caller sees and no test sets. "
        "Take the value as an option of the API, and let the binary read the environment.",
        environment_reads,
    ),
    Check(
        "dead-code",
        "An allowance for dead or unused code. Code that nothing uses is deleted, version control keeps it. "
        "An old path kept beside its replacement is the one the next reader copies.",
        dead_code_allowances,
    ),
]
