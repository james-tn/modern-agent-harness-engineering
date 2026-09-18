"""Validated configuration shared by the CLI, presets and local console."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .harness.capabilities import KEYWORDS
from .live_model import DEFAULT_DEPLOYMENT

OPTIONAL_TOOLS = ["public_source_search", "internal_api_lookup", "execute_analysis"]
ALL_SKILLS = sorted(KEYWORDS)


@dataclass
class HarnessConfig:
    model: str = "live"
    deployment: str = DEFAULT_DEPLOYMENT
    skill_mode: str = "progressive"
    available_skills: list[str] = field(default_factory=lambda: list(ALL_SKILLS))
    enabled_tools: list[str] = field(default_factory=lambda: list(OPTIONAL_TOOLS))
    memory_enabled: bool = True
    memory_scope: str = "techhub-analyst"
    max_model_requests: int = 40
    max_tool_calls: int = 60
    max_execution_attempts: int = 3
    execution_timeout_seconds: int = 15
    gate_mode: str = "strict"

    def __post_init__(self) -> None:
        for name, allowed in {
            "model": {"live", "scripted"},
            "deployment": {"gpt-5.6-terra", "gpt-5.4"},
            "skill_mode": {"progressive", "all_loaded"},
            "gate_mode": {"strict", "observe"},
        }.items():
            value = getattr(self, name)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"Invalid {name}; choose one of {sorted(allowed)}.")
        for name, allowed in (("available_skills", ALL_SKILLS), ("enabled_tools", OPTIONAL_TOOLS)):
            value = getattr(self, name)
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise ValueError(f"{name} must be a list of names.")
            if len(value) != len(set(value)) or set(value) - set(allowed):
                raise ValueError(f"{name} contains duplicates or unknown names.")
        if not isinstance(self.memory_enabled, bool):
            raise ValueError("memory_enabled must be boolean.")
        if not isinstance(self.memory_scope, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.memory_scope):
            raise ValueError("Memory scope must be 1-64 letters, digits, underscores or hyphens.")
        for name, low, high in (
            ("max_model_requests", 4, 60), ("max_tool_calls", 8, 100),
            ("max_execution_attempts", 1, 5), ("execution_timeout_seconds", 1, 30),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{name} must be an integer between {low} and {high}.")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HarnessConfig":
        if not isinstance(value, dict):
            raise ValueError("Harness configuration must be a JSON object.")
        unknown = set(value) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"Unknown configuration fields: {sorted(unknown)}")
        return cls(**value)


def profiles() -> dict[str, dict[str, Any]]:
    return {
        "governed": {
            "name": "Progressive / governed",
            "description": "Live model; on-demand skills and tools, shared memory, strict acceptance.",
            "config": HarnessConfig().to_dict(),
        },
        "naive": {
            "name": "All-loaded / observe-only",
            "description": "Live model; full skills and tools up front, no memory, checks observe preview.",
            "config": HarnessConfig(skill_mode="all_loaded", memory_enabled=False, gate_mode="observe").to_dict(),
        },
        "scripted": {
            "name": "Scripted / offline",
            "description": "No network. Seeded date near-miss; real tools, memory and gates. Not a live LLM.",
            "config": HarnessConfig(model="scripted", memory_scope="offline-rehearsal").to_dict(),
        },
    }
