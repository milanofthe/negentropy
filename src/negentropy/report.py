from __future__ import annotations

from negentropy.finding import Finding
from negentropy.rules import Rulebook


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


def render(findings: list[Finding], book: Rulebook, next_phase_only: bool = False) -> str:
    sections = [(rule, items([f for f in findings if f.check == rule.name])) for rule in book.rules]
    sections = [(rule, listed) for rule, listed in sections if listed]
    if not sections:
        return "negentropy: clean"
    total = sum(len(listed) for _, listed in sections)
    counts = ", ".join(f"{rule.name} {len(listed)}" for rule, listed in sections)
    blocks = [f"negentropy: {total} findings ({counts})"]
    shown = 0
    for number, phase in enumerate(book.phases, start=1):
        of_phase = [(rule, listed) for rule, listed in sections if rule.phase == phase.name]
        if not of_phase:
            continue
        blocks.append(f"# {number}. {phase.name.capitalize()}\n{phase.reason}")
        for rule, listed in of_phase:
            guidance = [rule.message, rule.cleanup] if rule.cleanup else [rule.message]
            blocks.append("\n".join([f"## {rule.name} ({len(listed)})", *guidance, "", *listed]))
            shown += len(listed)
        if next_phase_only:
            if total > shown:
                blocks.append(
                    f"The later phases have {total - shown} more findings. "
                    "Run `negentropy next` again when this phase is clean."
                )
            break
    return "\n\n".join(blocks)
