from __future__ import annotations

import subprocess
import tarfile
from functools import cached_property
from pathlib import Path

from negentropy.config import Config, matches
from negentropy.finding import ToolError


def git(root: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "core.quotepath=off", *args], cwd=root, capture_output=True, encoding="utf-8", errors="replace"
    )
    if done.returncode:
        raise ToolError(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def root_of(directory: Path) -> Path:
    return Path(git(directory, "rev-parse", "--show-toplevel").strip())


def has_revision(root: Path, revision: str) -> bool:
    done = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}"], cwd=root, capture_output=True
    )
    return done.returncode == 0


def export(root: Path, revision: str, directory: Path) -> list[str]:
    archive = subprocess.Popen(["git", "archive", "--format=tar", revision], cwd=root, stdout=subprocess.PIPE)
    exported = []
    with tarfile.open(fileobj=archive.stdout, mode="r|") as members:
        for member in members:
            if member.isfile():
                members.extract(member, directory, filter="data")
                exported.append(member.name)
    if archive.wait():
        raise ToolError(f"git archive {revision} failed")
    return exported


def changed_since(root: Path, revision: str) -> set[str]:
    changed = git(root, "diff", "--name-only", revision).splitlines()
    untracked = git(root, "ls-files", "--others", "--exclude-standard").splitlines()
    return set(changed) | set(untracked)


class Codebase:
    def __init__(self, root: Path, config: Config | None = None, files: list[str] | None = None):
        self.root = root
        self.config = config or Config.load(root)
        tracked_and_new = ("ls-files", "--cached", "--others", "--exclude-standard")
        listed = git(root, *tracked_and_new).splitlines() if files is None else files
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
