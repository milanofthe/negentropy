from __future__ import annotations

import re

TOKEN = re.compile(
    r"""//[^\n]*|/\*.*?\*/|\#[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_][A-Za-z_0-9]*|\d[\w.]*|\S""", re.S
)
KEPT = frozenset(
    "if else elif for while loop match return break continue in let mut fn def class try except finally raise "
    "with yield lambda not and or is as await async unsafe move ref where true false True False None".split()
)


def with_renamed_variables(function: str) -> tuple[str, ...]:
    tokens = [token for token in TOKEN.findall(function.partition("(")[2]) if not token.startswith(("//", "/*", "#"))]
    renamed: dict[str, int] = {}
    shape = []
    for index, token in enumerate(tokens):
        if not (token[0].isalpha() or token[0] == "_") or token in KEPT:
            shape.append(token)
        elif index + 1 < len(tokens) and tokens[index + 1] in ("(", "!") or index and tokens[index - 1] in (".", ":"):
            shape.append(token)
        else:
            shape.append(f"${renamed.setdefault(token, len(renamed))}")
    return tuple(shape)


def significant_digits(literal: str) -> int:
    mantissa = re.split(r"[eE]", re.sub(r"_|f32$|f64$|[jJ]$", "", literal))[0]
    return len(mantissa.replace(".", "").lstrip("0").rstrip("0"))
