from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

from negentropy.finding import ToolError

CONFIG_NAME = "negentropy.toml"


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
    markdown: tuple[str, ...] | None = None
    constants: tuple[str, ...] | None = None
    library: tuple[str, ...] | None = None
    exempt: tuple[str, ...] = ()
    rules: tuple[str, ...] = ()
    off: tuple[str, ...] = ()
    characters: str = ""
    budget: dict[str, int] = field(default_factory=dict)
    allow: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, root: Path) -> Config:
        path = root / CONFIG_NAME
        if not path.exists():
            return cls()
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
        unknown = set(raw) - {entry.name for entry in fields(cls)}
        if unknown:
            raise ToolError(f"{CONFIG_NAME}: unknown keys {sorted(unknown)}")
        return cls(**{key: tuple(value) if isinstance(value, list) else value for key, value in raw.items()})
