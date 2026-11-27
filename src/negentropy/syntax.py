from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sysconfig
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import yaml

from negentropy.finding import ToolError
from negentropy.rules import Selector

COMMAND_LINE_BUDGET = 24_000


@dataclass(frozen=True)
class Match:
    path: str
    lines: tuple[int, ...]
    text: str
    start: int | None = None
    end: int | None = None


def ast_grep() -> str:
    names = ("ast-grep", "ast-grep.exe")
    directories = {sysconfig.get_path("scripts")}
    with contextlib.suppress(KeyError, AttributeError):
        directories.add(sysconfig.get_path("scripts", f"{os.name}_user"))
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


def lines_of(found: dict) -> tuple[int, ...]:
    first, last = found["range"]["start"], found["range"]["end"]
    ends_on_its_last_line = last["column"] > 0 or last["line"] == first["line"]
    return tuple(range(first["line"] + 1, last["line"] + 1 + ends_on_its_last_line))


def parse(root: Path, files: list[str], selectors: list[Selector], languages: dict) -> dict[Selector, list[Match]]:
    documents, owners = [], {}
    for selector in selectors:
        for language in selector.languages:
            identifier = f"n{len(documents)}"
            owners[identifier] = selector
            documents.append({"id": identifier, "language": language, "rule": selector.rule})
    found: dict[Selector, list[Match]] = {selector: [] for selector in selectors}
    if not documents or not files:
        return found
    with tempfile.TemporaryDirectory() as directory:
        workspace = Path(directory)
        (workspace / "rules").mkdir()
        (workspace / "rules" / "all.yml").write_text(yaml.safe_dump_all(documents), encoding="utf-8")
        (workspace / "sgconfig.yml").write_text(
            yaml.safe_dump({"ruleDirs": ["rules"], "languageGlobs": languages}), encoding="utf-8"
        )

        def scan(paths: list[str]) -> list[dict]:
            done = subprocess.run(
                [ast_grep(), "scan", "--config", str(workspace / "sgconfig.yml"), "--json=stream", *paths],
                cwd=root, capture_output=True, encoding="utf-8", errors="replace",
            )
            if done.returncode and not done.stdout:
                raise ToolError(f"ast-grep: {done.stderr.strip()}")
            return [json.loads(line) for line in done.stdout.splitlines() if line]

        with ThreadPoolExecutor() as pool:
            entries = [entry for group in pool.map(scan, batches(files)) for entry in group]
    for entry in entries:
        span = entry["range"]["byteOffset"]
        path = entry["file"].replace("\\", "/").removeprefix("./")
        found[owners[entry["ruleId"]]].append(Match(path, lines_of(entry), entry["text"], span["start"], span["end"]))
    return found
