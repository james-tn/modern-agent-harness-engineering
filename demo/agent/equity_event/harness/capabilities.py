"""SELECT: choose predefined SKILL.md capabilities for this episode."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ALWAYS_ON = {"research-policy", "evidence-verification"}
CONFIDENCE_FLOOR = 0.15

KEYWORDS: dict[str, tuple[str, ...]] = {
    "equity-event-analysis": ("equity", "earnings", "event", "briefing"),
    "financial-source-retrieval": ("source", "filing", "web", "research"),
    "event-date-alignment": ("event", "date", "after close", "trading"),
    "abnormal-return-model": ("return", "benchmark", "market", "analysis"),
    "portfolio-impact": ("portfolio", "exposure", "position", "risk"),
    "research-policy": ("policy", "internal", "publish", "approval"),
    "interactive-briefing": ("chart", "graphic", "html", "briefing"),
    "evidence-verification": ("verify", "evidence", "complete", "test"),
    "options-surface-analysis": ("options", "volatility", "skew", "greeks"),
    "credit-event-analysis": ("credit", "bond", "spread", "rating"),
    "corporate-actions-monitor": ("dividend", "split", "merger", "tender"),
}

TOOLS: dict[str, tuple[str, ...]] = {
    "financial-source-retrieval": ("public_source_search", "internal_api_lookup"),
    "abnormal-return-model": ("write_analysis_script", "run_analysis_script"),
    "portfolio-impact": ("internal_api_lookup",),
    "interactive-briefing": ("write_analysis_script", "render_svg_dashboard"),
    "evidence-verification": ("verify_analysis",),
}


@dataclass(frozen=True)
class SkillInfo:
    name: str
    description: str
    path: Path


@dataclass
class Selection:
    goal: str
    selected: list[str]
    deferred: list[str]
    exposed_tools: list[str]
    confidence: float
    widened: bool
    paths: list[Path]

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "selected_skills": self.selected,
            "deferred_skills": self.deferred,
            "exposed_tools": self.exposed_tools,
            "selector_confidence": round(self.confidence, 3),
            "widened_on_low_confidence": self.widened,
            "catalog_size": len(self.selected) + len(self.deferred),
        }


def discover_skills(root: Path) -> list[SkillInfo]:
    skills: list[SkillInfo] = []
    for path in sorted(Path(root).glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+)$", text, re.MULTILINE)
        desc = re.search(r"^description:\s*(.+)$", text, re.MULTILINE)
        if not name or not desc:
            raise ValueError(f"Invalid SKILL.md frontmatter: {path}")
        skills.append(SkillInfo(name.group(1).strip(), desc.group(1).strip(), path.parent))
    if not skills:
        raise ValueError(f"No SKILL.md packages found under {root}")
    return skills


def select_skills(goal: str, root: Path, *, limit: int = 8) -> Selection:
    catalog = discover_skills(root)
    lower = goal.lower()
    scored = []
    for skill in catalog:
        words = KEYWORDS.get(skill.name, ())
        score = sum(1 for word in words if word in lower) / max(len(words), 1)
        scored.append((score, skill))
    scored.sort(key=lambda item: (-item[0], item[1].name))
    chosen = [skill for score, skill in scored if score > 0][:limit]
    selected_scores = [score for score, skill in scored if skill in chosen]
    deferred_scores = [score for score, skill in scored if skill not in chosen]
    confidence = min(selected_scores) - max(deferred_scores, default=0.0) if selected_scores else 0.0
    widened = confidence < CONFIDENCE_FLOOR
    if widened:
        chosen = [skill for score, skill in scored if score > 0][: limit + 1]
    for skill in catalog:
        if skill.name in ALWAYS_ON and skill not in chosen:
            chosen.append(skill)
    selected = [skill.name for skill in chosen]
    return Selection(
        goal=goal,
        selected=selected,
        deferred=[skill.name for skill in catalog if skill.name not in selected],
        exposed_tools=sorted({tool for name in selected for tool in TOOLS.get(name, ())}),
        confidence=confidence,
        widened=widened,
        paths=[skill.path for skill in chosen],
    )


def all_skill_paths(root: Path) -> list[Path]:
    return [skill.path for skill in discover_skills(root)]
