from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from negentropy.codebase import Codebase
from negentropy.config import matches
from negentropy.finding import Check, Finding

MARKDOWN_NAMES = re.compile(r"(?i)^(readme(\.[\w-]+)?|claude|agents|skill|license|notice|changelog)\.md$")
MARKDOWN_DIRECTORIES = (".github/", ".claude/")


def markdown(codebase: Codebase):
    for path in codebase.files:
        kept = (
            MARKDOWN_NAMES.match(Path(path).name)
            or path.startswith(MARKDOWN_DIRECTORIES)
            or matches(path, codebase.config.markdown)
        )
        if path.lower().endswith(".md") and not kept:
            yield Finding("markdown", path, 1)


def foreign_characters(text: str, allowed: str = "") -> list[str]:
    return sorted({char for char in text if not (char == "\t" or " " <= char <= "~" or char in allowed)})


def named(characters: list[str]) -> str:
    return ", ".join(f"U+{ord(char):04X} {unicodedata.name(char, 'UNNAMED')}" for char in characters)


def characters(codebase: Codebase):
    for path, lines in codebase.texts.items():
        for number, text in enumerate(lines, start=1):
            if foreign := foreign_characters(text, codebase.config.characters):
                yield Finding("characters", path, number, named(foreign))


CHECKS = [
    Check(
        "markdown",
        "A markdown file that is not a README. A plan, a note or a finding goes into an issue, where it has a "
        "date and gets closed; a file in the tree is read as the current state long after it stopped being it. "
        "Markdown that is content is listed in negentropy.toml (`markdown`).",
        markdown,
    ),
    Check(
        "characters",
        "A character outside ASCII. Typographic characters (dashes, curly quotes, arrows, non-breaking spaces) "
        "are written with their ASCII form. The letters a project writes in are listed in negentropy.toml "
        "(`characters`).",
        characters,
    ),
]
