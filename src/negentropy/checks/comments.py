from __future__ import annotations

import re

from negentropy.codebase import Codebase
from negentropy.config import matches
from negentropy.finding import Check, Finding

SOURCE_LINK = re.compile(r"https?://\S+")
LICENSE_HEADER = re.compile(r"SPDX-License-Identifier|Copyright \(c\)|Copyright \d{4}|Licensed under")
SCRIPT_DIRECTIVES = re.compile(
    r"eslint-|@ts-(expect-error|ignore|nocheck|check)|prettier-ignore|biome-ignore|(c8|v8|istanbul) ignore"
    r"|@vite-ignore|[#@]__PURE__|webpack[A-Z]|svelte-ignore|^///\s*<reference"
)
TOOL_DIRECTIVES = {
    "rust": re.compile(r"^//\s*SAFETY:"),
    "python": re.compile(r"^#(!|\s*(type:|noqa|pragma:|fmt:|ruff:|pylint:|mypy:|pyright:|isort:|-\*-))"),
    "javascript": SCRIPT_DIRECTIVES,
    "typescript": SCRIPT_DIRECTIVES,
    "tsx": SCRIPT_DIRECTIVES,
    "html": re.compile(r"svelte-ignore|prettier-ignore"),
    "css": re.compile(r"stylelint-|prettier-ignore"),
    "bash": re.compile(r"^#!|shellcheck "),
    "yaml": re.compile(r"^#!|^#cloud-config|yaml-language-server|prettier-ignore"),
}

ON_INTERNAL_ITEM = "on an internal item"
OUTSIDE_PUBLIC_API = "outside the public API"


def comments(codebase: Codebase):
    for match in codebase.syntax.of_kind("comment"):
        language = match.rule.split("-")[1]
        kept = SOURCE_LINK.search(match.text) or LICENSE_HEADER.search(match.text)
        if not kept and not TOOL_DIRECTIVES[language].search(match.text):
            yield from (Finding("comment", match.path, line) for line in match.lines)


def doc_comments(codebase: Codebase):
    public = codebase.config.public
    internal = set()
    for match in codebase.syntax.of_kind("doc"):
        if match.rule.startswith("doc-internal-"):
            internal.update((match.path, line) for line in match.lines)
            yield from (Finding("doc-comment", match.path, line, ON_INTERNAL_ITEM) for line in match.lines)
    for match in codebase.syntax.of_kind("doc"):
        outside = public is not None and not matches(match.path, public)
        if outside and not match.rule.startswith("doc-internal-"):
            yield from (
                Finding("doc-comment", match.path, line, OUTSIDE_PUBLIC_API)
                for line in match.lines
                if (match.path, line) not in internal
            )


CHECKS = [
    Check(
        "comment",
        "A comment in code. Nothing checks a comment, so it goes stale and the next reader trusts it. "
        "Delete it and let the code say it: a name, a type, an assertion or a test. "
        "A constraint from outside the repository stays, with a link to its source.",
        comments,
    ),
    Check(
        "doc-comment",
        "A doc comment that is not API documentation. Doc comments stay on the items the language exports, "
        "inside the paths negentropy.toml lists as `public`. Delete it; if the item needs explaining, "
        "rename or restructure it.",
        doc_comments,
    ),
]
