from __future__ import annotations

import uuid
from collections import Counter

from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord

HEURISTIC_SOURCE_TYPES = {"project_learning", "task_pattern", "regression"}
MIN_PATTERN_COUNT = 3


class HeuristicEngine:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db

    def generate(self) -> list[MemoryRecord]:
        source_memories: list[MemoryRecord] = []
        for memory_type in HEURISTIC_SOURCE_TYPES:
            source_memories.extend(self.db.list_memories(memory_type=memory_type, limit=200))

        groups: dict[tuple[str, str], list[MemoryRecord]] = {}
        for memory in source_memories:
            key = (memory.scope, memory.memory_type)
            groups.setdefault(key, []).append(memory)

        heuristics: list[MemoryRecord] = []
        for (scope, memory_type), memories in groups.items():
            if len(memories) < MIN_PATTERN_COUNT:
                continue

            tag_counts = Counter(tag for mem in memories for tag in mem.tags)
            dominant_tags = [tag for tag, count in tag_counts.most_common(3) if count >= MIN_PATTERN_COUNT]
            if not dominant_tags:
                continue

            existing_heuristics = self.db.list_memories(
                memory_type="heuristic", scope=scope, limit=20
            )
            tag_set = frozenset(dominant_tags)
            already_exists = any(
                frozenset(h.tags) & tag_set for h in existing_heuristics
            )
            if already_exists:
                continue

            pattern_tag = dominant_tags[0]
            count = len(memories)
            heuristic = MemoryRecord(
                memory_id=f"heur_{uuid.uuid4().hex[:8]}",
                memory_type="heuristic",
                scope=scope,
                title=f"Pattern: {pattern_tag} on {scope} ({count} occurrences)",
                content=f"When working on {scope}, '{pattern_tag}' events occurred "
                        f"{count} times across {memory_type} memories. "
                        f"Dominant tags: {', '.join(dominant_tags)}. "
                        f"Consider adjusting strategy for this pattern.",
                tags=dominant_tags,
                confidence=min(0.9, 0.5 + count * 0.05),
                linked_memories=[m.memory_id for m in memories[:5]],
            )
            heuristics.append(heuristic)
            self.db.upsert_memory(heuristic)

        return heuristics
