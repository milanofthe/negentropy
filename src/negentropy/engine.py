from __future__ import annotations

import re
import unicodedata
from functools import cached_property
from typing import Iterator

from negentropy.codebase import Codebase
from negentropy.config import CONFIG_NAME, matches
from negentropy.finding import Finding
from negentropy.rules import Rule, Rulebook, Selector
from negentropy.structure import resemblances, significant_digits, with_renamed_variables
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
        self.matched: set[int] = set()
        self.spans: dict[str, dict[str, list[tuple[int, int]]]] = {}

    @cached_property
    def parsed(self) -> dict[Selector, list[Match]]:
        of_rules = [selector for rule in self.book.about("codebase") for selector in rule.selectors]
        of_scopes = [selector for scope in self.book.scopes.values() for selector in scope.selectors]
        syntactic = [selector for selector in of_rules + of_scopes if selector.rule is not None]
        return parse(self.codebase.root, self.codebase.files, syntactic, self.book.languages)

    def ranges(self, name: str) -> dict[str, list[tuple[int, int]]]:
        if name not in self.spans:
            self.spans[name] = {}
            for selector in self.book.scopes[name].selectors:
                for match in self.selected(selector):
                    self.spans[name].setdefault(match.path, []).append((match.start, match.end))
        return self.spans[name]

    def inside(self, name: str, match: Match) -> bool:
        scope = self.book.scopes[name]
        if scope.everywhere or matches(match.path, scope.paths):
            return True
        spans = self.ranges(name).get(match.path, ())
        return match.start is not None and any(start <= match.start < end for start, end in spans)

    def raw(self, selector: Selector) -> Iterator[Match]:
        files = self.codebase.files
        if selector.rule is not None:
            yield from self.parsed[selector]
        elif selector.file:
            yield from (Match(path, (1,), path) for path in files if matches(path, selector.file))
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

    def located(self, match: Match) -> str:
        lines = self.codebase.texts.get(match.path, [])
        source = lines[match.lines[0] - 1] if match.lines[0] <= len(lines) else ""
        return f"{match.path}: {source}"

    def allowed(self, rule: Rule, match: Match) -> bool:
        patterns = self.codebase.config.allow.get(rule.name, ())
        return any(re.search(pattern, self.located(match)) for pattern in patterns)

    def reason(self, rule: Rule, match: Match) -> str:
        for index, entry in enumerate(self.codebase.config.reported):
            if entry["check"] == rule.name and re.search(entry["match"], self.located(match)):
                self.matched.add(index)
                return entry["reason"]
        return ""

    def found(self, rule: Rule, selector: Selector) -> Iterator[Match]:
        return (match for match in self.selected(selector) if not self.allowed(rule, match))

    def each(self, rule: Rule) -> Iterator[Finding]:
        seen = set()
        for selector in rule.selectors:
            for match in self.found(rule, selector):
                detail = names_of(selector, match.text) if selector.names else selector.detail
                reason = self.reason(rule, match)
                for line in match.lines:
                    if (match.path, line) not in seen:
                        seen.add((match.path, line))
                        yield Finding(rule.name, match.path, line, detail, reason)

    def unique(self, rule: Rule) -> Iterator[Finding]:
        found = [match for selector in rule.selectors for match in self.found(rule, selector)]
        first: dict[tuple[str, ...], Match] = {}
        for match in sorted(found, key=lambda match: (match.path, match.lines[0])):
            shape = with_renamed_variables(match.text)
            if len(shape) < rule.tokens:
                continue
            if shape in first:
                original = first[shape]
                detail = f"identical to {original.path}:{original.lines[0]}"
                yield Finding(rule.name, match.path, match.lines[0], detail, self.reason(rule, match))
            else:
                first[shape] = match
        if not rule.similar:
            return
        long = [
            (match, shape)
            for shape, match in first.items()
            if len(shape) >= rule.similar_tokens and not any(self.inside(name, match) for name in rule.similar_outside)
        ]
        nearest: dict[int, tuple[float, int]] = {}
        for (one, other), ratio in resemblances([shape for _, shape in long], rule.similar).items():
            nearest[other] = max(nearest.get(other, (0.0, one)), (ratio, one))
        for other, (ratio, one) in sorted(nearest.items()):
            match, original = long[other][0], long[one][0]
            detail = f"{int(100 * ratio)} percent identical to {original.path}:{original.lines[0]}"
            yield Finding(rule.name, match.path, match.lines[0], detail, self.reason(rule, match))

    def unmatched(self, rule: Rule) -> Iterator[Finding]:
        lines = self.codebase.texts.get(CONFIG_NAME, [])
        headers = [n for n, text in enumerate(lines, start=1) if re.match(r"\s*\[\[reported\]\]", text)]
        for index, entry in enumerate(self.codebase.config.reported):
            if index not in self.matched:
                line = headers[index] if index < len(headers) else 1
                yield Finding(rule.name, CONFIG_NAME, line, f"{entry['check']}: {entry['match']}")

    def findings(self) -> list[Finding]:
        rules = self.book.about("codebase")
        kinds = {"each": self.each, "unique": self.unique}
        found = [finding for rule in rules if rule.kind in kinds for finding in kinds[rule.kind](rule)]
        return found + [finding for rule in rules if rule.kind == "unmatched" for finding in self.unmatched(rule)]


def findings(codebase: Codebase) -> list[Finding]:
    return Engine(codebase).findings()
