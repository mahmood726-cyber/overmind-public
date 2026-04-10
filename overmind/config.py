from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Expected mapping in {path}")
    return loaded


@dataclass(slots=True)
class ScanRules:
    include_git_repos: bool = True
    include_non_git_apps: bool = True
    incremental_scan: bool = True
    max_depth: int = 5


@dataclass(slots=True)
class RootsConfig:
    scan_roots: list[Path] = field(default_factory=list)
    scan_rules: ScanRules = field(default_factory=ScanRules)
    guidance_filenames: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RunnerDefinition:
    runner_id: str
    type: str
    mode: str
    command: str
    environment: str
    optional: bool = False


@dataclass(slots=True)
class PoliciesConfig:
    concurrency: dict[str, int | float] = field(default_factory=dict)
    limits: dict[str, int | float] = field(default_factory=dict)
    routing: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    risk_policy: dict[str, list[str]] = field(default_factory=dict)
    isolation: dict[str, str] = field(default_factory=lambda: {"mode": "none"})

    def strengths_for(self, runner_type: str) -> list[str]:
        return list(self.routing.get(runner_type, {}).get("strengths", []))


@dataclass(slots=True)
class VerificationRule:
    profile: str
    match_name_equals: list[str] = field(default_factory=list)
    match_path_contains: list[str] = field(default_factory=list)
    match_project_type: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AppConfig:
    config_dir: Path
    data_dir: Path
    db_path: Path
    roots: RootsConfig
    runners: list[RunnerDefinition]
    policies: PoliciesConfig
    ignored_directories: list[str]
    ignored_file_suffixes: list[str]
    verification_profiles: dict[str, list[str]]
    verification_rules: list[VerificationRule]

    @classmethod
    def from_directory(
        cls,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
        db_path: Path | None = None,
    ) -> "AppConfig":
        package_root = Path(__file__).resolve().parents[1]
        config_dir = Path(
            os.environ.get("OVERMIND_CONFIG_DIR", str(config_dir or package_root / "config"))
        )
        data_dir = Path(
            os.environ.get("OVERMIND_DATA_DIR", str(data_dir or package_root / "data"))
        )
        db_path = Path(
            os.environ.get("OVERMIND_DB_PATH", str(db_path or data_dir / "state" / "overmind.db"))
        )

        roots_payload = _load_yaml(config_dir / "roots.yaml")
        runners_payload = _load_yaml(config_dir / "runners.yaml")
        policies_payload = _load_yaml(config_dir / "policies.yaml")
        ignores_payload = _load_yaml(config_dir / "projects_ignore.yaml")
        verification_payload = _load_yaml(config_dir / "verification_profiles.yaml")

        roots = RootsConfig(
            scan_roots=[Path(entry) for entry in roots_payload.get("scan_roots", [])],
            scan_rules=ScanRules(**roots_payload.get("scan_rules", {})),
            guidance_filenames=list(roots_payload.get("guidance_filenames", [])),
        )

        runners = [RunnerDefinition(**entry) for entry in runners_payload.get("runners", [])]
        policies = PoliciesConfig(
            concurrency=dict(policies_payload.get("concurrency", {})),
            limits=dict(policies_payload.get("limits", {})),
            routing=dict(policies_payload.get("routing", {})),
            risk_policy=dict(policies_payload.get("risk_policy", {})),
            isolation=dict(policies_payload.get("isolation", {"mode": "none"})),
        )

        verification_profiles = {
            name: list(payload.get("required", []))
            for name, payload in verification_payload.get("profiles", {}).items()
        }
        verification_rules = [
            VerificationRule(
                profile=entry["profile"],
                match_name_equals=list(entry.get("match_name_equals", [])),
                match_path_contains=list(entry.get("match_path_contains", [])),
                match_project_type=list(entry.get("match_project_type", [])),
            )
            for entry in verification_payload.get("project_rules", [])
        ]

        config = cls(
            config_dir=config_dir,
            data_dir=data_dir,
            db_path=db_path,
            roots=roots,
            runners=runners,
            policies=policies,
            ignored_directories=list(ignores_payload.get("ignored_directories", [])),
            ignored_file_suffixes=list(ignores_payload.get("ignored_file_suffixes", [])),
            verification_profiles=verification_profiles,
            verification_rules=verification_rules,
        )
        config.ensure_directories()
        return config

    def ensure_directories(self) -> None:
        self.config_dir.mkdir(parents=True, exist_ok=True)
        for directory in (
            self.data_dir,
            self.data_dir / "state",
            self.data_dir / "transcripts",
            self.data_dir / "checkpoints",
            self.data_dir / "artifacts",
            self.data_dir / "logs",
            self.data_dir / "cache",
        ):
            directory.mkdir(parents=True, exist_ok=True)
