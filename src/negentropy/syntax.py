from __future__ import annotations

import json
import os
import shutil
import subprocess
import sysconfig
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from negentropy.finding import ToolError

PACKAGE = Path(__file__).resolve().parent
COMMAND_LINE_BUDGET = 24_000
LANGUAGES = {
    ".rs", ".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx",
    ".svelte", ".html", ".css", ".sh", ".bash", ".yml", ".yaml",
}


@dataclass(frozen=True)
class Match:
    rule: str
    path: str
    text: str
    lines: tuple[int, ...]
    offset: int

    @property
    def kind(self) -> str:
        return self.rule.split("-")[0]


def ast_grep() -> str:
    names = ("ast-grep", "ast-grep.exe")
    directories = {sysconfig.get_path("scripts"), sysconfig.get_path("scripts", f"{os.name}_user")}
    candidates = [Path(directory) / name for directory in directories for name in names]
    found = next((str(path) for path in candidates if path.exists()), None) or shutil.which("ast-grep")
    if not found:
        raise ToolError("ast-grep is not installed: pip install ast-grep-cli")
    return found


def batches(paths: list[str]) -> list[list[str]]:
    grouped, size = [[]], 0
    for path in paths:
        if size + len(path) + 1 > COMMAND_LINE_BUDGET and grouped[-1]:
            grouped.append([])
            size = 0
        grouped[-1].append(path)
        size += len(path) + 1
    return [group for group in grouped if group]


def scan(root: Path, paths: list[str]) -> list[dict]:
    done = subprocess.run(
        [ast_grep(), "scan", "--config", str(PACKAGE / "sgconfig.yml"), "--json=stream", *paths],
        cwd=root, capture_output=True, encoding="utf-8", errors="replace",
    )
    if done.returncode and not done.stdout:
        raise ToolError(f"ast-grep: {done.stderr.strip()}")
    return [json.loads(line) for line in done.stdout.splitlines() if line]


def lines_of(found: dict) -> tuple[int, ...]:
    first, last = found["range"]["start"], found["range"]["end"]
    ends_on_its_last_line = last["column"] > 0 or last["line"] == first["line"]
    return tuple(range(first["line"] + 1, last["line"] + 1 + ends_on_its_last_line))


@dataclass
class Syntax:
    matches: list[Match]
    scopes: dict[tuple[str, str], list[tuple[int, int]]]

    @classmethod
    def of(cls, root: Path, files: list[str]) -> Syntax:
        parsed = [path for path in files if Path(path).suffix in LANGUAGES]
        with ThreadPoolExecutor() as pool:
            found = [entry for group in pool.map(lambda paths: scan(root, paths), batches(parsed)) for entry in group]
        matches, scopes = [], {}
        for entry in found:
            path = entry["file"].replace("\\", "/").removeprefix("./")
            span = entry["range"]["byteOffset"]
            if entry["ruleId"].startswith("scope-"):
                scopes.setdefault((path, entry["ruleId"].split("-")[1]), []).append((span["start"], span["end"]))
            else:
                matches.append(Match(entry["ruleId"], path, entry["text"], lines_of(entry), span["start"]))
        return cls(matches, scopes)

    def within(self, scope: str, match: Match) -> bool:
        return any(start <= match.offset < end for start, end in self.scopes.get((match.path, scope), []))

    def of_kind(self, *kinds: str) -> list[Match]:
        return [match for match in self.matches if match.kind in kinds]
