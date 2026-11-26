from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

from negentropy.finding import ToolError

CONFIG_NAME = "negentropy.toml"

CONSTANTS_PATHS = ("**/constants.rs", "**/constants/**", "**/constants.py")
LIBRARY_PATHS = ("**/src/**",)
TEST_PATHS = (
    "**/tests/**", "**/benches/**", "**/examples/**", "**/tests.rs",
    "**/test_*.py", "**/*_test.py", "**/conftest.py",
    "**/*.test.ts", "**/*.test.js", "**/*.spec.ts", "**/*.spec.js",
)
BINARY_PATHS = ("**/main.rs", "**/bin/**", "**/build.rs", "**/cli.rs", "**/cli/**")


@lru_cache(maxsize=None)
def glob_pattern(glob: str) -> re.Pattern[str]:
    parts = re.split(r"(\*\*/|\*\*|\*|\?)", glob)
    translated = {"**/": "(.*/)?", "**": ".*", "*": "[^/]*", "?": "[^/]"}
    return re.compile("".join(translated.get(part, re.escape(part)) for part in parts) + r"\Z")


def matches(path: str, globs) -> bool:
    return any(glob_pattern(glob).match(path) for glob in globs)


@dataclass(frozen=True)
class Config:
    public: tuple[str, ...] | None = None
    markdown: tuple[str, ...] = ()
    exempt: tuple[str, ...] = ()
    constants: tuple[str, ...] = CONSTANTS_PATHS
    library: tuple[str, ...] = LIBRARY_PATHS
    off: tuple[str, ...] = ()
    characters: str = ""

    @classmethod
    def load(cls, root: Path) -> Config:
        path = root / CONFIG_NAME
        if not path.exists():
            return cls()
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        unknown = set(raw) - {entry.name for entry in fields(cls)}
        if unknown:
            raise ToolError(f"{CONFIG_NAME}: unknown keys {sorted(unknown)}")
        return cls(**{key: value if isinstance(value, str) else tuple(value) for key, value in raw.items()})
