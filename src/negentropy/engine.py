from __future__ import annotations

import re
import tomllib
import unicodedata
from functools import cached_property
from typing import Iterator

from negentropy.codebase import Codebase
from negentropy.config import CONFIG_NAME, matches
from negentropy.finding import Finding, ToolError
from negentropy.rules import Rule, Rulebook, Selector
from negentropy.structure import significant_digits, with_renamed_variables
from negentropy.syntax import Match, parse


def without(text: str, allowed: str) -> str:
    return text.translate({ord(char): None for char in allowed}) if allowed else text


def names_of(selector: Selector, text: str) -> str:
    characters = sorted(set("".join(selector.line.findall(text))))
    return ", ".join(f"U+{ord(char):04X} {unicodedata.name(char, 'UNNAMED')}" for char in characters)


class Engine:
    def __init__(self, codebase: Codebase, book: Rulebook | None = None):
        self.codebase = codebase
        self.book = book or Rulebook.load(codebase.root, codebase.config)

    @cached_property
    def parsed(self) -> dict[Selector, list[Match]]:
        of_rules = [selector for rule in self.book.about("codebase") for selector in rule.all_selectors]
        of_scopes = [selector for scope in self.book.scopes.values() for selector in scope.selectors]
        syntactic = [selector for selector in of_rules + of_scopes if selector.rule is not None]
        return parse(self.codebase.root, self.codebase.files, syntactic, self.book.languages)

    @cached_property
    def ranges(self) -> dict[tuple[str, str], list[tuple[int, int]]]:
        ranges: dict[tuple[str, str], list[tuple[int, int]]] = {}
        for name, scope in self.book.scopes.items():
            for selector in scope.selectors:
                for match in self.parsed[selector]:
                    ranges.setdefault((name, match.path), []).append((match.start, match.end))
        return ranges

    def inside(self, name: str, match: Match) -> bool:
        scope = self.book.scopes[name]
        if scope.everywhere or matches(match.path, scope.paths):
            return True
        spans = self.ranges.get((name, match.path), ())
        return match.start is not None and any(start <= match.start < end for start, end in spans)

    def raw(self, selector: Selector) -> Iterator[Match]:
        files = self.codebase.files
        if selector.rule is not None:
            yield from self.parsed[selector]
        elif selector.file:
            yield from (Match(path, (1,), path) for path in files if matches(path, selector.file))
        elif selector.keys is not None:
            for path in files:
                if matches(path, selector.files):
                    table = tomllib.loads((self.codebase.root / path).read_text(encoding="utf-8"))
                    yield from (Match(path, (1,), key) for key in table.get(selector.keys, {}))
        else:
            allowed = getattr(self.codebase.config, selector.allow) if selector.allow else ""
            for path, lines in self.codebase.texts.items():
                if selector.files and not matches(path, selector.files):
                    continue
                for number, text in enumerate(lines, start=1):
                    shown = without(text, allowed)
                    if selector.line.search(shown):
                        yield Match(path, (number,), shown)

    def selected(self, selector: Selector) -> Iterator[Match]:
        for match in self.raw(selector):
            if selector.matches and not selector.matches.search(match.text):
                continue
            if any(pattern.search(match.text) for pattern in selector.unless):
                continue
            digits = significant_digits(match.text) if selector.digits_over or selector.digits_up_to else 0
            if selector.digits_over is not None and digits <= selector.digits_over:
                continue
            if selector.digits_up_to is not None and digits > selector.digits_up_to:
                continue
            if all(self.inside(name, match) for name in selector.within) and not any(
                self.inside(name, match) for name in selector.outside
            ):
                yield match

    def each(self, rule: Rule) -> Iterator[Finding]:
        seen = set()
        for selector in rule.selectors:
            for match in self.selected(selector):
                detail = names_of(selector, match.text) if selector.names else selector.detail
                for line in match.lines:
                    if (match.path, line) not in seen:
                        seen.add((match.path, line))
                        yield Finding(rule.name, match.path, line, detail)

    def unique(self, rule: Rule) -> Iterator[Finding]:
        found = [match for selector in rule.selectors for match in self.selected(selector)]
        first: dict[tuple[str, ...], Match] = {}
        for match in sorted(found, key=lambda match: (match.path, match.lines[0])):
            shape = with_renamed_variables(match.text)
            if len(shape) < rule.tokens:
                continue
            if shape in first:
                original = first[shape]
                yield Finding(rule.name, match.path, match.lines[0], f"the same as {original.path}:{original.lines[0]}")
            else:
                first[shape] = match

    def count(self, rule: Rule) -> Iterator[Finding]:
        lines = self.codebase.texts.get(CONFIG_NAME, [])
        for name, declared in self.codebase.config.budget.items():
            if name not in rule.counts:
                continue
            counted = sum(1 for selector in rule.counts[name] for _ in self.selected(selector))
            if counted != declared:
                line = next((n for n, text in enumerate(lines, start=1) if re.match(rf"\s*{name}\s*=", text)), 1)
                yield Finding(rule.name, CONFIG_NAME, line, f"{name}: {counted} in the codebase, {declared} declared")

    def findings(self) -> list[Finding]:
        rules = self.book.about("codebase")
        countable = {name for rule in rules for name in rule.counts}
        unknown = set(self.codebase.config.budget) - countable
        if unknown:
            raise ToolError(f"{CONFIG_NAME}: `budget` counts {sorted(countable)}, not {sorted(unknown)}")
        kinds = {"each": self.each, "unique": self.unique, "count": self.count}
        return [finding for rule in rules for finding in kinds[rule.kind](rule)]


def findings(codebase: Codebase) -> list[Finding]:
    return Engine(codebase).findings()
