from __future__ import annotations

from negentropy.finding import Finding
from negentropy.rules import Rule


def items(findings: list[Finding]) -> list[str]:
    ordered = sorted(set(findings))
    lines, index = [], 0
    while index < len(ordered):
        first = last = ordered[index]
        while index + 1 < len(ordered) and ordered[index + 1] == Finding(
            last.check, last.path, last.line + 1, last.detail
        ):
            index += 1
            last = ordered[index]
        span = f"{first.line}" if first is last else f"{first.line}-{last.line}"
        detail = f"  {first.detail}" if first.detail else ""
        lines.append(f"- [ ] {first.path}:{span}{detail}")
        index += 1
    return lines


def render(findings: list[Finding], rules: tuple[Rule, ...]) -> str:
    sections = [(rule, items([f for f in findings if f.check == rule.name])) for rule in rules]
    sections = [(rule, listed) for rule, listed in sections if listed]
    if not sections:
        return "negentropy: clean"
    total = sum(len(listed) for _, listed in sections)
    counts = ", ".join(f"{rule.name} {len(listed)}" for rule, listed in sections)
    blocks = [f"negentropy: {total} findings ({counts})"]
    for rule, listed in sections:
        blocks.append("\n".join([f"## {rule.name} ({len(listed)})", rule.message, "", *listed]))
    return "\n\n".join(blocks)
