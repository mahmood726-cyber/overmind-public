"""Voyager-style Skill Library for fix recipes.

Upgrades the Evolution Manager's recipe tracking into a retrievable,
composable skill library. Each proven recipe becomes a "skill" indexed
by natural-language description for retrieval when similar failures occur.

Inspired by Voyager (NeurIPS 2023): generate skills, validate through
execution, store verified skills, retrieve compositionally.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from overmind.evolution.recipe import Recipe


@dataclass
class Skill:
    """A validated fix recipe promoted to reusable skill.

    Two-level abstraction (Mem^p pattern):
    - fix_script: concrete steps ("pip install scipy")
    - abstract_strategy: higher-level pattern ("dependency rot → check if external → pip install")
    """
    skill_id: str
    failure_type: str
    pattern: str
    description: str  # Natural-language description for retrieval
    fix_script: str   # Concrete fix command or code
    abstract_strategy: str = ""  # Mem^p: higher-level strategy
    confidence: float = 0.0
    durability: float = 1.0  # PRAXIS: how often fix holds over time
    contrastive_diff: str = ""  # MACLA: what changed between fail→success
    times_used: int = 0
    times_succeeded: int = 0
    created_from_recipe: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        if self.times_used == 0:
            return self.confidence
        return self.times_succeeded / self.times_used

    def to_dict(self) -> dict:
        return {
            "skill_id": self.skill_id,
            "failure_type": self.failure_type,
            "pattern": self.pattern,
            "description": self.description,
            "fix_script": self.fix_script,
            "abstract_strategy": self.abstract_strategy,
            "confidence": self.confidence,
            "durability": self.durability,
            "contrastive_diff": self.contrastive_diff,
            "times_used": self.times_used,
            "times_succeeded": self.times_succeeded,
            "created_from_recipe": self.created_from_recipe,
            "tags": self.tags,
        }


class SkillLibrary:
    """Persistent skill library with natural-language retrieval."""

    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        self.skills: dict[str, Skill] = {}
        self._load()

    def promote_recipe(self, recipe: Recipe) -> Skill | None:
        """Promote a proven recipe to a reusable skill."""
        if not recipe.is_proven():
            return None
        if recipe.recipe_id in self.skills:
            return self.skills[recipe.recipe_id]

        skill = Skill(
            skill_id=recipe.recipe_id,
            failure_type=recipe.failure_type,
            pattern=recipe.pattern,
            description=f"Fix {recipe.failure_type}: {recipe.fix_description}",
            fix_script=recipe.fix_description,
            abstract_strategy=recipe.abstract_strategy or f"{recipe.failure_type} → {recipe.fix_description[:50]}",
            confidence=recipe.confidence,
            durability=recipe.durability,
            contrastive_diff=recipe.contrastive_diff,
            created_from_recipe=recipe.recipe_id,
            tags=[recipe.failure_type, recipe.pattern[:20]],
        )
        self.skills[skill.skill_id] = skill
        self._save()
        return skill

    def retrieve(self, failure_type: str, evidence: str, top_k: int = 3) -> list[Skill]:
        """Retrieve skills matching a failure type and evidence pattern.

        Uses simple keyword matching + failure type filtering.
        Could be upgraded to embedding-based retrieval.
        """
        candidates = []
        evidence_lower = evidence.lower()

        for skill in self.skills.values():
            score = 0.0

            # Exact failure type match
            if skill.failure_type == failure_type:
                score += 3.0

            # Pattern match in evidence
            if skill.pattern and skill.pattern.lower() in evidence_lower:
                score += 5.0

            # Tag match
            for tag in skill.tags:
                if tag.lower() in evidence_lower:
                    score += 1.0

            # Confidence and success rate boost
            score += skill.success_rate * 2.0

            # Decay: penalize skills that haven't been used recently
            if skill.times_used > 5 and skill.success_rate < 0.5:
                score *= 0.3  # Demote failing skills

            if score > 0:
                candidates.append((score, skill))

        candidates.sort(key=lambda x: -x[0])
        return [skill for _, skill in candidates[:top_k]]

    def record_outcome(self, skill_id: str, success: bool) -> None:
        """Record whether a skill application succeeded."""
        if skill_id in self.skills:
            self.skills[skill_id].times_used += 1
            if success:
                self.skills[skill_id].times_succeeded += 1
            self._save()

    def compose(self, skill_ids: list[str]) -> list[Skill]:
        """Retrieve skills by ID for chained execution."""
        return [self.skills[sid] for sid in skill_ids if sid in self.skills]

    def demote_stale(self, min_uses: int = 5, max_failure_rate: float = 0.7) -> int:
        """Demote skills that have stopped working."""
        demoted = 0
        to_remove = []
        for skill_id, skill in self.skills.items():
            if skill.times_used >= min_uses:
                if (skill.times_used - skill.times_succeeded) / skill.times_used > max_failure_rate:
                    to_remove.append(skill_id)
                    demoted += 1
        for sid in to_remove:
            del self.skills[sid]
        if demoted:
            self._save()
        return demoted

    def stats(self) -> dict:
        return {
            "total_skills": len(self.skills),
            "by_type": {},
            "avg_confidence": sum(s.confidence for s in self.skills.values()) / max(len(self.skills), 1),
            "total_uses": sum(s.times_used for s in self.skills.values()),
            "total_successes": sum(s.times_succeeded for s in self.skills.values()),
        }

    def _load(self) -> None:
        if not self.library_path.exists():
            return
        try:
            data = json.loads(self.library_path.read_text(encoding="utf-8"))
            for entry in data.get("skills", []):
                skill = Skill(**entry)
                self.skills[skill.skill_id] = skill
        except (json.JSONDecodeError, TypeError):
            pass

    def _save(self) -> None:
        data = {"skills": [s.to_dict() for s in self.skills.values()]}
        self.library_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
