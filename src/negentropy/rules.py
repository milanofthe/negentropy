from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from negentropy.config import Config
from negentropy.finding import ToolError

PACKAGE = Path(__file__).resolve().parent
SELECTOR_KEYS = {
    "language", "rule", "line", "file", "keys", "files", "allow", "names", "after_subject",
    "matches", "unless", "in", "not_in", "detail", "digits_over", "digits_up_to",
}
SHARED_KEYS = {"matches", "unless", "in", "not_in", "detail", "digits_over", "digits_up_to"}
RULE_KEYS = SHARED_KEYS | {"name", "message", "kind", "subject", "select", "counts", "tokens", "unless_subject"}
KINDS = {"each", "unique", "count"}


def listed(value) -> tuple:
    if value is None:
        return ()
    return tuple(value) if isinstance(value, (list, tuple)) else (value,)


@dataclass(frozen=True, eq=False)
class Selector:
    languages: tuple[str, ...] = ()
    rule: dict | None = None
    line: re.Pattern | None = None
    file: tuple[str, ...] = ()
    keys: str | None = None
    files: tuple[str, ...] = ()
    allow: str | None = None
    names: bool = False
    after_subject: bool = False
    matches: re.Pattern | None = None
    unless: tuple[re.Pattern, ...] = ()
    within: tuple[str, ...] = ()
    outside: tuple[str, ...] = ()
    detail: str = ""
    digits_over: int | None = None
    digits_up_to: int | None = None

    @classmethod
    def of(cls, raw: dict, shared: dict, source: str) -> Selector:
        unknown = set(raw) - SELECTOR_KEYS
        if unknown:
            raise ToolError(f"{source}: a selector has unknown keys {sorted(unknown)}")
        if sum(key in raw for key in ("rule", "line", "file", "keys")) != 1:
            raise ToolError(f"{source}: a selector must have exactly one of the keys rule, line, file and keys")
        merged = {**shared, **raw}
        return cls(
            languages=listed(raw.get("language")),
            rule=raw.get("rule"),
            line=re.compile(raw["line"]) if "line" in raw else None,
            file=listed(raw.get("file")),
            keys=raw.get("keys"),
            files=listed(raw.get("files")),
            allow=raw.get("allow"),
            names=bool(raw.get("names")),
            after_subject=bool(raw.get("after_subject")),
            matches=re.compile(merged["matches"]) if "matches" in merged else None,
            unless=tuple(re.compile(text) for text in listed(shared.get("unless")) + listed(raw.get("unless"))),
            within=listed(shared.get("in")) + listed(raw.get("in")),
            outside=listed(shared.get("not_in")) + listed(raw.get("not_in")),
            detail=merged.get("detail", ""),
            digits_over=merged.get("digits_over"),
            digits_up_to=merged.get("digits_up_to"),
        )


def selectors(raw: dict, source: str) -> tuple[Selector, ...]:
    shared = {key: raw[key] for key in SHARED_KEYS if key in raw}
    return tuple(Selector.of(entry, shared, source) for entry in raw.get("select", []))


@dataclass(frozen=True, eq=False)
class Rule:
    name: str
    message: str
    kind: str = "each"
    subjects: tuple[str, ...] = ("codebase",)
    selectors: tuple[Selector, ...] = ()
    counts: dict[str, tuple[Selector, ...]] = field(default_factory=dict)
    tokens: int = 0
    unless_subject: re.Pattern | None = None

    @classmethod
    def load(cls, path: Path) -> Rule:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        source = path.name
        unknown = set(raw) - RULE_KEYS
        if unknown or "name" not in raw or "message" not in raw:
            raise ToolError(f"{source}: a check needs a name and a message; unknown keys: {sorted(unknown)}")
        kind = raw.get("kind", "each")
        if kind not in KINDS:
            raise ToolError(f"{source}: kind must be one of {sorted(KINDS)}")
        return cls(
            name=raw["name"],
            message=raw["message"],
            kind=kind,
            subjects=listed(raw.get("subject", "codebase")),
            selectors=selectors(raw, source),
            counts={name: selectors(entry, source) for name, entry in raw.get("counts", {}).items()},
            tokens=raw.get("tokens", 0),
            unless_subject=re.compile(raw["unless_subject"]) if "unless_subject" in raw else None,
        )

    @property
    def all_selectors(self) -> tuple[Selector, ...]:
        return self.selectors + tuple(entry for group in self.counts.values() for entry in group)


@dataclass(frozen=True, eq=False)
class Scope:
    paths: tuple[str, ...] = ()
    selectors: tuple[Selector, ...] = ()
    everywhere: bool = False


@dataclass(frozen=True, eq=False)
class Rulebook:
    rules: tuple[Rule, ...]
    scopes: dict[str, Scope]
    languages: dict[str, list[str]]

    @classmethod
    def load(cls, root: Path, config: Config) -> Rulebook:
        base = yaml.safe_load((PACKAGE / "base.yml").read_text(encoding="utf-8"))
        rules = [Rule.load(PACKAGE / "checks" / f"{name}.yml") for name in base["checks"]]
        for directory in config.rules:
            rules += [Rule.load(path) for path in sorted((root / directory).glob("*.yml"))]
        names = [rule.name for rule in rules]
        unknown = set(config.off) - set(names)
        if unknown or len(names) != len(set(names)):
            raise ToolError(f"check names must be unique, and `off` may only list existing checks; unknown: {sorted(unknown)}")
        scopes = {}
        for name, raw in base["scopes"].items():
            configured = getattr(config, raw["config"]) if "config" in raw else None
            fallback = raw.get("default")
            paths = configured if configured is not None else fallback
            scopes[name] = Scope(
                paths=listed(raw.get("paths")) + listed(paths),
                selectors=selectors(raw, f"scope {name}"),
                everywhere="config" in raw and paths is None,
            )
        book = cls(tuple(rule for rule in rules if rule.name not in config.off), scopes, base["languages"])
        for rule in book.rules:
            for selector in rule.all_selectors:
                missing = set(selector.within + selector.outside) - set(scopes)
                if missing:
                    raise ToolError(f"{rule.name}: unknown scopes {sorted(missing)}; the existing scopes are {sorted(scopes)}")
        return book

    def about(self, subject: str) -> list[Rule]:
        return [rule for rule in self.rules if subject in rule.subjects]
