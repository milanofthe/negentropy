from __future__ import annotations

from negentropy.finding import Check, Finding


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


def render(findings: list[Finding], checks: list[Check]) -> str:
    sections = [(check, items([f for f in findings if f.check == check.name])) for check in checks]
    sections = [(check, listed) for check, listed in sections if listed]
    if not sections:
        return "negentropy: clean"
    total = sum(len(listed) for _, listed in sections)
    counts = ", ".join(f"{check.name} {len(listed)}" for check, listed in sections)
    blocks = [f"negentropy: {total} to fix ({counts})"]
    for check, listed in sections:
        blocks.append("\n".join([f"## {check.name} ({len(listed)})", check.message, "", *listed]))
    return "\n\n".join(blocks)
