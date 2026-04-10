from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SCRIPT_BROWSER_HINTS = ("playwright", "e2e", "cypress")
SCRIPT_PERF_HINTS = ("lighthouse", "perf", "benchmark")
STACK_HINTS = {
    "vite": "vite",
    "webpack": "webpack",
    "parcel": "parcel",
    "react": "react",
    "vue": "vue",
    "svelte": "svelte",
    "playwright": "playwright",
}


def _package_manager(root: Path, package_json: dict[str, Any]) -> str:
    package_manager = str(package_json.get("packageManager", "")).lower()
    if package_manager.startswith("pnpm") or (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if package_manager.startswith("yarn") or (root / "yarn.lock").exists():
        return "yarn"
    return "npm"


def _script_command(package_manager: str, script_name: str) -> str:
    if package_manager == "yarn":
        return f"yarn {script_name}"
    return f"{package_manager} run {script_name}"


class ManifestParser:
    def parse(self, root: Path) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "stack": [],
            "build_commands": [],
            "test_commands": [],
            "browser_test_commands": [],
            "perf_commands": [],
            "package_manager": "npm",
            "manifest_hash": "",
        }

        package_path = root / "package.json"
        data: dict[str, Any] = {}
        if package_path.exists():
            raw_text = package_path.read_text(encoding="utf-8-sig", errors="ignore")
            payload["manifest_hash"] = hashlib.sha1(raw_text.encode("utf-8")).hexdigest()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                return payload
            package_manager = _package_manager(root, data)
            payload["package_manager"] = package_manager
            scripts = data.get("scripts", {})

            if "build" in scripts:
                payload["build_commands"].append(_script_command(package_manager, "build"))
            if "test" in scripts:
                payload["test_commands"].append(_script_command(package_manager, "test"))

            for script_name, script_body in scripts.items():
                lowered = f"{script_name} {script_body}".lower()
                if any(hint in lowered for hint in SCRIPT_BROWSER_HINTS):
                    command = _script_command(package_manager, script_name)
                    if command not in payload["browser_test_commands"]:
                        payload["browser_test_commands"].append(command)
                if any(hint in lowered for hint in SCRIPT_PERF_HINTS):
                    command = _script_command(package_manager, script_name)
                    if command not in payload["perf_commands"]:
                        payload["perf_commands"].append(command)

            dependencies = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            stack = set()
            for dependency in dependencies:
                lowered = dependency.lower()
                for hint, label in STACK_HINTS.items():
                    if hint in lowered:
                        stack.add(label)
            payload["stack"] = sorted(stack)

        if (root / "index.html").exists():
            payload["stack"] = sorted(set(payload["stack"]) | {"html", "javascript", "css"})

        for candidate in (
            "playwright.config.js",
            "playwright.config.ts",
            "playwright.config.mjs",
        ):
            if (root / candidate).exists():
                payload["browser_test_commands"] = payload["browser_test_commands"] or ["npx playwright test"]
                payload["stack"] = sorted(set(payload["stack"]) | {"playwright"})

        return payload
