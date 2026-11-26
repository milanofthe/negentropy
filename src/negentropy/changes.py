from __future__ import annotations

import re
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from difflib import SequenceMatcher
from pathlib import Path

import yaml

from negentropy.codebase import Codebase, export, git, has_revision
from negentropy.config import Config
from negentropy.engine import Engine
from negentropy.finding import ToolError
from negentropy.rules import PACKAGE, Rule, Rulebook, Selector, selectors
from negentropy.structure import resemblances, with_renamed_variables
from negentropy.syntax import Match

SHOWN_CHARACTERS = 100
CHANGE_KEYS = {"name", "compare", "message", "select", "named", "value", "through", "lines", "similar", "tokens"}
WORD = re.compile(r"\b[A-Za-z_]\w*\b")


@dataclass(frozen=True, eq=False)
class Change:
    name: str
    message: str
    compare: str
    selectors: tuple[Selector, ...] = ()
    named: re.Pattern | None = None
    value: re.Pattern | None = None
    through: str = ""
    lines: bool = False
    similar: float = 1.0
    tokens: int = 0

    @classmethod
    def of(cls, raw: dict) -> Change:
        unknown = set(raw) - CHANGE_KEYS
        if unknown or raw.get("compare") not in COMPARISONS:
            raise ToolError(f"changes.yml: {raw.get('name')} has unknown keys {sorted(unknown)} or an unknown comparison")
        return cls(
            name=raw["name"],
            message=raw["message"],
            compare=raw["compare"],
            selectors=selectors(raw, "changes.yml"),
            named=re.compile(raw["named"], re.M) if "named" in raw else None,
            value=re.compile(raw["value"]) if "value" in raw else None,
            through=raw.get("through", ""),
            lines=bool(raw.get("lines")),
            similar=raw.get("similar", 1.0),
            tokens=raw.get("tokens", 0),
        )

    def name_of(self, match: Match) -> str:
        found = self.named.search(match.text) if self.named else None
        return next((group for group in found.groups() if group), "") if found else ""

    def values_of(self, match: Match) -> list[str]:
        if self.value is None:
            return [" ".join(match.text.split())]
        return self.value.findall(match.text)


class Side:
    def __init__(self, root: Path, changes: tuple[Change, ...], files: list[str] | None = None):
        self.config = Config.load(root)
        book = Rulebook.load(root, self.config)
        rules = tuple(Rule(change.name, change.message, selectors=change.selectors) for change in changes)
        self.engine = Engine(Codebase(root, self.config, files), replace(book, rules=rules))
        self.changes = {change.name: change for change in changes}
        self.selected: dict[str, list[Match]] = {}

    def matches(self, change: Change) -> list[Match]:
        if change.name not in self.selected:
            found = [match for selector in change.selectors for match in self.engine.selected(selector)]
            self.selected[change.name] = sorted(found, key=lambda match: (match.path, match.lines[0]))
        return self.selected[change.name]

    def values_of(self, change: Change, match: Match) -> list[str]:
        values = change.values_of(match)
        if change.through:
            other = self.changes[change.through]
            texts = {other.name_of(named): named.text for named in self.matches(other)}
            for word in set(WORD.findall(match.text)) & texts.keys():
                values += change.value.findall(texts[word])
        return sorted(values)


def shortened(text: str) -> str:
    return text if len(text) <= SHOWN_CHARACTERS else text[: SHOWN_CHARACTERS - 3] + "..."


def located(match: Match, detail: str) -> str:
    return f"- {match.path}:{match.lines[0]}  {detail}"


def similarity(one: tuple[str, ...], other: tuple[str, ...], least: float) -> float:
    compared = SequenceMatcher(None, one, other, autojunk=False)
    return compared.ratio() if compared.quick_ratio() >= least else 0.0


def gone(change: Change, before: Side, now: Side) -> list[str]:
    old, new = before.matches(change), now.matches(change)
    old_names, new_names = ({change.name_of(match) for match in side} for side in (old, new))
    removed = [match for match in old if change.name_of(match) not in new_names]
    added = [with_renamed_variables(match.text) for match in new if change.name_of(match) not in old_names]
    scored = sorted(
        (
            (similarity(with_renamed_variables(match.text), shape, change.similar), index, successor)
            for index, match in enumerate(removed)
            for successor, shape in enumerate(added)
        ),
        reverse=True,
    )
    succeeded: set[int] = set()
    taken: set[int] = set()
    for score, index, successor in scored:
        if score >= change.similar and index not in succeeded and successor not in taken:
            succeeded.add(index)
            taken.add(successor)
    return [located(match, change.name_of(match)) for index, match in enumerate(removed) if index not in succeeded]


def paired(change: Change, before: list[Match], now: list[Match]) -> list[tuple[Match, Match]]:
    old = {(match.path, change.name_of(match)): match for match in before}
    new = {(match.path, change.name_of(match)): match for match in now}
    pairs = [(old[key], new[key]) for key in old.keys() & new.keys()]

    def moved(side: dict, other: dict) -> dict[str, Match]:
        left = [(name, match) for (path, name), match in side.items() if (path, name) not in other]
        names = [name for name, _ in left]
        return {name: match for name, match in left if names.count(name) == 1}

    moved_old, moved_new = moved(old, new), moved(new, old)
    pairs += [(moved_old[name], moved_new[name]) for name in moved_old.keys() & moved_new.keys()]
    return sorted(pairs, key=lambda pair: (pair[1].path, pair[1].lines[0]))


def changed(change: Change, before: Side, now: Side) -> list[str]:
    listed = []
    for old, new in paired(change, before.matches(change), now.matches(change)):
        was, is_now = before.values_of(change, old), now.values_of(change, new)
        if was and Counter(is_now) - Counter(was):
            shown = f"{shortened(', '.join(was))} -> {shortened(', '.join(is_now))}"
            listed.append(located(new, f"{change.name_of(new)}: {shown}"))
    return listed


def more(change: Change, before: Side, now: Side) -> list[str]:
    def per_file(side: Side) -> dict[str, int]:
        counted: dict[str, int] = {}
        for match in side.matches(change):
            counted[match.path] = counted.get(match.path, 0) + (len(match.lines) if change.lines else 1)
        return counted

    old, new = per_file(before), per_file(now)
    if sum(new.values()) <= sum(old.values()):
        return []
    unit = " lines" if change.lines else ""
    return [f"- {path}  {old.get(path, 0)} -> {count}{unit}" for path, count in sorted(new.items()) if count > old.get(path, 0)]


def resembles(change: Change, before: Side, now: Side) -> list[str]:
    old = before.matches(change)
    old_places = {(match.path, change.name_of(match)) for match in old}
    old_shapes = {with_renamed_variables(match.text) for match in old}
    shaped = [(match, with_renamed_variables(match.text)) for match in now.matches(change)]
    shaped = [(match, shape) for match, shape in shaped if len(shape) >= change.tokens]
    new = {
        number
        for number, (match, shape) in enumerate(shaped)
        if (match.path, change.name_of(match)) not in old_places and shape not in old_shapes
    }
    nearest: dict[int, tuple[float, int]] = {}
    for (one, other), ratio in resemblances([shape for _, shape in shaped], change.similar).items():
        for written, partner in ((one, other), (other, one)):
            if written in new and ratio < 1.0:
                nearest[written] = max(nearest.get(written, (0.0, partner)), (ratio, partner))
    listed = []
    for written, (ratio, partner) in sorted(nearest.items()):
        match, other = shaped[written][0], shaped[partner][0]
        detail = f"{change.name_of(match)}: {int(100 * ratio)} percent like {change.name_of(other)} at {other.path}:{other.lines[0]}"
        listed.append(located(match, detail))
    return listed


def config(change: Change, before: Side, now: Side) -> list[str]:
    old, new = before.config, now.config
    listed = [
        f"- allow {check}: {pattern}"
        for check, patterns in sorted(new.allow.items())
        for pattern in patterns
        if pattern not in old.allow.get(check, ())
    ]
    listed += [f"- exempt: {glob}" for glob in new.exempt if glob not in old.exempt]
    listed += [f"- off: {check}" for check in new.off if check not in old.off]
    return listed


COMPARISONS = {"gone": gone, "changed": changed, "more": more, "resembles": resembles, "config": config}


def report(root: Path, revision: str) -> str:
    raw = yaml.safe_load((PACKAGE / "changes.yml").read_text(encoding="utf-8"))
    changes = tuple(Change.of(entry) for entry in raw["changes"])
    if not has_revision(root, revision):
        return f"negentropy: {revision} is not a revision, so there is nothing to compare with"
    base = git(root, "merge-base", revision, "HEAD").strip()
    with tempfile.TemporaryDirectory() as directory:
        files = export(root, base, Path(directory))
        before, now = Side(Path(directory), changes, files), Side(root, changes)
        sections = [(change, COMPARISONS[change.compare](change, before, now)) for change in changes]
    sections = [(change, listed) for change, listed in sections if listed]
    if not sections:
        return f"negentropy: no changes since {revision} that the owner needs to review"
    counts = ", ".join(f"{change.name} {len(listed)}" for change, listed in sections)
    blocks = [f"negentropy: changes since {revision} for the owner to review ({counts})", raw["intro"]]
    blocks += ["\n".join([f"## {change.name} ({len(listed)})", change.message, "", *listed]) for change, listed in sections]
    return "\n\n".join(blocks)
