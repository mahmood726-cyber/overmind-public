from __future__ import annotations

from overmind.discovery.guidance_parser import GuidanceParser


def test_guidance_parser_extracts_commands_and_redacts_secrets(tmp_path):
    (tmp_path / "CLAUDE.md").write_text(
        "# Project Rules\n"
        "- Never ship without tests\n"
        "```bash\n"
        "python -m pytest -q\n"
        "node test.js\n"
        "```\n"
        "API key example: AIzaSyFAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0\n",
        encoding="utf-8",
    )

    result = GuidanceParser().load(tmp_path, ["claude.md", "README.md"])

    assert result.found == ["claude.md"]
    assert "python -m pytest -q" in result.commands
    assert "node test.js" in result.commands
    assert "AIza" not in "\n".join(result.summary)
