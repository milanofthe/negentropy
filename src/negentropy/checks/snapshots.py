from __future__ import annotations

import re

from negentropy.codebase import Codebase
from negentropy.finding import Check, Finding

MANIFESTS = re.compile(r"(^|/)(Cargo\.toml|pyproject\.toml|requirements[\w.-]*\.txt|package\.json)$")
SNAPSHOT_LIBRARIES = re.compile(
    r"\b(insta|expect[-_]test|goldenfile|syrupy|pytest-regressions|pytest-snapshot|snapshottest|jest-snapshot)\b"
)
SNAPSHOT_ASSERTIONS = re.compile(r"assert_\w*snapshot|expect!\[\[|toMatch(Inline)?Snapshot")


def snapshots(codebase: Codebase):
    for path in codebase.files:
        if path.endswith(".snap"):
            yield Finding("snapshot", path, 1)
    for path, lines in codebase.texts.items():
        pattern = SNAPSHOT_LIBRARIES if MANIFESTS.search(path) else SNAPSHOT_ASSERTIONS
        for number, text in enumerate(lines, start=1):
            if pattern.search(text):
                yield Finding("snapshot", path, number)


CHECKS = [
    Check(
        "snapshot",
        "A snapshot test. A snapshot fixes the output the code had when it was recorded, right or wrong. "
        "Assert the contract instead: a reference, an invariant, the API.",
        snapshots,
    ),
]
