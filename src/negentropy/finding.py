from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable

if TYPE_CHECKING:
    from negentropy.codebase import Codebase


@dataclass(frozen=True, order=True)
class Finding:
    check: str
    path: str
    line: int
    detail: str = ""


@dataclass(frozen=True)
class Check:
    name: str
    message: str
    find: Callable[[Codebase], Iterable[Finding]] | None = None


class ToolError(Exception):
    pass
