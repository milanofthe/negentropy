from __future__ import annotations

import subprocess
from functools import cached_property
from pathlib import Path

from negentropy.config import TEST_PATHS, Config, matches
from negentropy.finding import ToolError
from negentropy.syntax import Match, Syntax


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace"
    )
    if done.returncode:
        raise ToolError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def root_of(directory: Path) -> Path:
    return Path(git(directory, "rev-parse", "--show-toplevel").strip())


class Codebase:
    def __init__(self, root: Path, config: Config | None = None):
        self.root = root
        self.config = config or Config.load(root)
        listed = git(root, "ls-files", "--cached", "--others", "--exclude-standard").splitlines()
        self.files = sorted(
            path for path in set(listed) if (root / path).is_file() and not matches(path, self.config.exempt)
        )

    @cached_property
    def texts(self) -> dict[str, list[str]]:
        texts = {}
        for path in self.files:
            data = (self.root / path).read_bytes()
            if b"\0" in data:
                continue
            try:
                texts[path] = data.decode("utf-8").splitlines()
            except UnicodeDecodeError:
                continue
        return texts

    @cached_property
    def syntax(self) -> Syntax:
        return Syntax.of(self.root, self.files)

    def in_test(self, match: Match) -> bool:
        return matches(match.path, TEST_PATHS) or self.syntax.within("test", match)

    def in_library(self, match: Match) -> bool:
        return matches(match.path, self.config.library) and not self.in_test(match)
