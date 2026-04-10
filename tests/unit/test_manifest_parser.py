from __future__ import annotations

import json

from overmind.discovery.manifest_parser import ManifestParser


def test_manifest_parser_extracts_commands_and_stack(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "packageManager": "pnpm@9.0.0",
                "scripts": {
                    "build": "vite build",
                    "test": "vitest run",
                    "test:e2e": "playwright test",
                    "perf": "lighthouse http://localhost:4173",
                },
                "dependencies": {"react": "^18.0.0", "vite": "^5.0.0"},
                "devDependencies": {"@playwright/test": "^1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")

    parsed = ManifestParser().parse(tmp_path)

    assert parsed["package_manager"] == "pnpm"
    assert parsed["build_commands"] == ["pnpm run build"]
    assert parsed["test_commands"] == ["pnpm run test"]
    assert "pnpm run test:e2e" in parsed["browser_test_commands"]
    assert "pnpm run perf" in parsed["perf_commands"]
    assert {"react", "vite", "playwright", "html", "javascript", "css"}.issubset(set(parsed["stack"]))
    assert parsed["manifest_hash"]

