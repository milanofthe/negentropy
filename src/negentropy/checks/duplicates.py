from __future__ import annotations

import re

from negentropy.codebase import Codebase
from negentropy.finding import Check, Finding

DUPLICATE_TOKENS = 25
TOKEN = re.compile(
    r"""//[^\n]*|/\*.*?\*/|\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_][A-Za-z_0-9]*|\d[\w.]*|\S""", re.S
)
CONTROL = frozenset(
    "if else elif for while loop match return break continue in let mut fn def class try except finally raise "
    "with yield lambda not and or is as await async unsafe move ref where true false True False None".split()
)


def structure(function: str) -> tuple[str, ...]:
    tokens = [token for token in TOKEN.findall(function.partition("(")[2]) if not token.startswith(("//", "/*", "#"))]
    renamed: dict[str, int] = {}
    shape = []
    for index, token in enumerate(tokens):
        if not (token[0].isalpha() or token[0] == "_") or token in CONTROL:
            shape.append(token)
        elif index + 1 < len(tokens) and tokens[index + 1] in ("(", "!") or index and tokens[index - 1] in (".", ":"):
            shape.append(token)
        else:
            shape.append(f"${renamed.setdefault(token, len(renamed))}")
    return tuple(shape)


def duplicates(codebase: Codebase):
    first: dict[tuple[str, ...], tuple[str, int]] = {}
    functions = sorted(codebase.syntax.of_kind("function"), key=lambda match: (match.path, match.lines[0]))
    for match in functions:
        shape = structure(match.text)
        if len(shape) < DUPLICATE_TOKENS:
            continue
        if shape in first:
            path, line = first[shape]
            yield Finding("duplicate", match.path, match.lines[0], f"the same as {path}:{line}")
        else:
            first[shape] = (match.path, match.lines[0])


CHECKS = [
    Check(
        "duplicate",
        "A function that is another one with its variables renamed. Keep one and call it from both places; "
        "if the copies should differ, the difference is a parameter. Before writing a helper, search for the "
        "one that exists.",
        duplicates,
    ),
]
