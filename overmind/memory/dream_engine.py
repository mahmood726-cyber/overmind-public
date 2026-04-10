from __future__ import annotations

from overmind.memory.heuristic_engine import HeuristicEngine
from overmind.storage.db import StateDatabase
from overmind.storage.models import MemoryRecord, utc_now

STALE_RELEVANCE_THRESHOLD = 0.1
DUPLICATE_SIMILARITY_THRESHOLD = 0.6


class DreamEngine:
    def __init__(self, db: StateDatabase) -> None:
        self.db = db
        self.heuristic_engine = HeuristicEngine(db)

    def dream(self) -> dict[str, object]:
        memories_before = len(self.db.list_memories(status="active", limit=10000, include_expired=True))
        expired = self.db.expire_memories()
        heuristics = self._phase_extract_heuristics()
        merges = self._phase_consolidate()
        archives = self._phase_prune()
        memories_after = len(self.db.list_memories(status="active", limit=10000))

        summary: dict[str, object] = {
            "last_dream_at": utc_now(),
            "memories_before": memories_before,
            "memories_after": memories_after,
            "merges": merges,
            "heuristics_generated": len(heuristics),
            "archives": archives,
            "expired": expired,
        }
        self.db.write_checkpoint("dream", summary)
        return summary

    def should_dream(self, ticks_since_last: int, active_memory_count: int) -> bool:
        return ticks_since_last >= 5 and active_memory_count >= 10

    def _phase_consolidate(self) -> int:
        all_memories = self.db.list_memories(status="active", limit=10000)
        groups: dict[tuple[str, str], list[MemoryRecord]] = {}
        for memory in all_memories:
            key = (memory.scope, memory.memory_type)
            groups.setdefault(key, []).append(memory)

        merge_count = 0
        for group_memories in groups.values():
            if len(group_memories) < 2:
                continue
            merged_ids: set[str] = set()
            for i, mem_a in enumerate(group_memories):
                if mem_a.memory_id in merged_ids:
                    continue
                for mem_b in group_memories[i + 1:]:
                    if mem_b.memory_id in merged_ids:
                        continue
                    if self._similar(mem_a, mem_b):
                        mem_a.content = f"{mem_a.content} {mem_b.content}"
                        mem_a.relevance = round(max(mem_a.relevance, mem_b.relevance), 4)
                        mem_a.confidence = round(max(mem_a.confidence, mem_b.confidence), 4)
                        for tag in mem_b.tags:
                            if tag not in mem_a.tags:
                                mem_a.tags.append(tag)
                        if mem_b.memory_id not in mem_a.linked_memories:
                            mem_a.linked_memories.append(mem_b.memory_id)
                        mem_a.updated_at = utc_now()
                        mem_b.status = "merged"
                        mem_b.updated_at = utc_now()
                        self.db.upsert_memory(mem_b)
                        merged_ids.add(mem_b.memory_id)
                        merge_count += 1
                if mem_a.memory_id not in merged_ids:
                    self.db.upsert_memory(mem_a)

        return merge_count

    def _phase_extract_heuristics(self) -> list[MemoryRecord]:
        return self.heuristic_engine.generate()

    def _phase_prune(self) -> int:
        return self.db.archive_stale_memories(STALE_RELEVANCE_THRESHOLD)

    def _similar(self, a: MemoryRecord, b: MemoryRecord) -> bool:
        words_a = set(a.title.lower().split())
        words_b = set(b.title.lower().split())
        union = words_a | words_b
        if not union:
            return False
        overlap = len(words_a & words_b)
        return overlap / len(union) >= DUPLICATE_SIMILARITY_THRESHOLD
