"""Versioned deterministic Requirement parsing baseline."""

import re
from dataclasses import dataclass

from job_hunter.domain.screening import RequirementPriority, RequirementType

_BULLET_PREFIX = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s*")


def _normalized(value: str) -> str:
    return " ".join(value.split())


@dataclass(frozen=True, slots=True)
class RequirementDraft:
    source_text: str
    text: str
    requirement_type: RequirementType
    priority: RequirementPriority


class DeterministicRequirementParser:
    name = "deterministic-line-parser"
    version = "1"

    def parse(self, description: str) -> tuple[RequirementDraft, ...]:
        lines: list[str] = []
        seen: set[str] = set()
        for raw_line in description.splitlines():
            line = _normalized(_BULLET_PREFIX.sub("", raw_line))
            key = line.casefold()
            if line and key not in seen:
                seen.add(key)
                lines.append(line)
        if not lines:
            lines = [_normalized(description)]
        return tuple(
            RequirementDraft(
                source_text=line,
                text=line,
                requirement_type=self._requirement_type(line),
                priority=self._priority(line),
            )
            for line in lines
        )

    @staticmethod
    def _priority(text: str) -> RequirementPriority:
        normalized = text.casefold()
        if any(token in normalized for token in ("preferred", "nice to have", "优先", "加分")):
            return RequirementPriority.PREFERRED
        if any(token in normalized for token in ("must", "required", "要求", "必须")):
            return RequirementPriority.REQUIRED
        return RequirementPriority.UNSPECIFIED

    @staticmethod
    def _requirement_type(text: str) -> RequirementType:
        normalized = text.casefold()
        if any(token in normalized for token in ("python", "langgraph", "llm", "skill", "技能")):
            return RequirementType.SKILL
        if any(token in normalized for token in ("degree", "bachelor", "master", "学历", "本科")):
            return RequirementType.EDUCATION
        if any(token in normalized for token in ("experience", "years", "经验", "年")):
            return RequirementType.EXPERIENCE
        if any(token in normalized for token in ("location", "remote", "on-site", "地点", "城市")):
            return RequirementType.LOCATION
        if any(token in normalized for token in ("build", "develop", "design", "负责", "开发")):
            return RequirementType.RESPONSIBILITY
        return RequirementType.OTHER
