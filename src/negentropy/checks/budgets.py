from __future__ import annotations

import re
import tomllib

from negentropy.codebase import Codebase
from negentropy.config import CONFIG_NAME, matches
from negentropy.finding import Check, Finding, ToolError


def constants(codebase: Codebase) -> int:
    found = codebase.syntax.of_kind("constant")
    return sum(1 for match in found if matches(match.path, codebase.config.constants) and not codebase.in_test(match))


def features(codebase: Codebase) -> int:
    count = 0
    for path in codebase.files:
        if path.rsplit("/", 1)[-1] == "Cargo.toml":
            manifest = tomllib.loads((codebase.root / path).read_text(encoding="utf-8"))
            count += sum(1 for name in manifest.get("features", {}) if name != "default")
    return count


COUNTED = {"constants": constants, "features": features}


def budgets(codebase: Codebase):
    declared = codebase.config.budget
    unknown = set(declared) - set(COUNTED)
    if unknown:
        raise ToolError(f"{CONFIG_NAME}: `budget` counts {sorted(COUNTED)}, not {sorted(unknown)}")
    lines = codebase.texts.get(CONFIG_NAME, [])
    for name, limit in declared.items():
        count = COUNTED[name](codebase)
        if count != limit:
            line = next((n for n, text in enumerate(lines, start=1) if re.match(rf"\s*{name}\s*=", text)), 1)
            yield Finding("budget", CONFIG_NAME, line, f"{name}: {count} in the codebase, {limit} declared")


CHECKS = [
    Check(
        "budget",
        "A count that differs from the one negentropy.toml declares. More of them is a decision for the owner "
        "of that file, not for the change that adds one: remove another, or ask. Fewer: lower the number.",
        budgets,
    ),
]
