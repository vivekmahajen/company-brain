"""Render a compiled skill to Anthropic-style SKILL.md (YAML frontmatter + body)."""
from __future__ import annotations


def _yaml_scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def render_skill_md(frontmatter: dict, body_md: str) -> str:
    fm = frontmatter
    lines = ["---"]
    lines.append(f"slug: {fm['slug']}")
    lines.append(f"title: {fm['title']}")
    lines.append("description: >-")
    for chunk in _wrap(fm["description"], 72):
        lines.append(f"  {chunk}")
    lines.append(f"version: {fm['version']}")
    lines.append(f"status: {fm['status']}")

    lines.append("inputs:")
    for inp in fm.get("inputs", []):
        lines.append(f"  - {inp}")

    lines.append("tools:")
    for t in fm.get("tools", []):
        lines.append(f"  - name: {t['name']}")
        lines.append(f"    side_effecting: {_yaml_scalar(t['side_effecting'])}")
        lines.append(f"    approval_required_when: \"{t.get('approval_required_when', 'never')}\"")

    lines.append("guardrails:")
    for g in fm.get("guardrails", []):
        lines.append(f"  - {g}")

    lines.append("provenance:")
    for p in fm.get("provenance", []):
        lines.append(f"  - ku: {p['ku']}  source: {p['source']}  span: \"{p['span']}\"")

    lines.append("---")
    lines.append("")
    lines.append(body_md.rstrip())
    lines.append("")
    return "\n".join(lines)


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    out, cur = [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out or [""]
