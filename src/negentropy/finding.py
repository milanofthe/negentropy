from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, order=True)
class Finding:
    check: str
    path: str
    line: int
    detail: str = ""
    reason: str = ""


class ToolError(Exception):
    pass
