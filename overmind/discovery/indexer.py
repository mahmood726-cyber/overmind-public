from __future__ import annotations

import json

from overmind.config import AppConfig
from overmind.discovery.project_scanner import ProjectScanner
from overmind.storage.db import StateDatabase
from overmind.storage.models import ProjectRecord

CACHE_VERSION = 8


class ProjectIndexer:
    def __init__(self, config: AppConfig, db: StateDatabase) -> None:
        self.config = config
        self.db = db
        self.scanner = ProjectScanner(config)
        self.cache_path = self.config.data_dir / "cache" / "indexer_state.json"

    def incremental_refresh(self, focus_project_id: str | None = None) -> list[ProjectRecord]:
        cache = self._load_cache()
        next_cache: dict[str, object] = {"cache_version": CACHE_VERSION, "projects": {}}
        records: list[ProjectRecord] = []

        for root in self.scanner.discover_project_roots():
            root_key = str(root)
            signature = self.scanner.compute_signature(root)
            cached = cache.get("projects", {}).get(root_key)
            if cached and cached.get("signature") == signature:
                record = ProjectRecord(**cached["record"])
            else:
                record = self.scanner.scan_project(root)

            next_cache["projects"][root_key] = {
                "signature": signature,
                "record": record.to_dict(),
            }
            if focus_project_id and record.project_id != focus_project_id:
                continue
            records.append(record)
            self.db.upsert_project(record)

        self._save_cache(next_cache)
        return records

    def _load_cache(self) -> dict[str, object]:
        if not self.cache_path.exists():
            return {}
        with self.cache_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if payload.get("cache_version") != CACHE_VERSION:
            return {}
        return payload

    def _save_cache(self, payload: dict[str, object]) -> None:
        with self.cache_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
