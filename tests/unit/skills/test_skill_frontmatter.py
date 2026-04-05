from pathlib import Path

import yaml


SKILL_FILES = (
    Path("skills/redis-cve-report/SKILL.md"),
    Path("skills/redis-inspection-report/SKILL.md"),
    Path("skills/redis-rdb-analysis/SKILL.md"),
)


def test_skill_markdown_files_start_with_yaml_frontmatter() -> None:
    for path in SKILL_FILES:
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), f"{path} must start with YAML frontmatter"
        assert not text.startswith("```yaml"), f"{path} must not wrap frontmatter in a fenced code block"


def test_skill_frontmatter_is_parseable_and_has_required_fields() -> None:
    for path in SKILL_FILES:
        text = path.read_text(encoding="utf-8")
        _, frontmatter_text, _ = text.split("---", 2)
        frontmatter = yaml.safe_load(frontmatter_text)
        assert isinstance(frontmatter, dict), f"{path} frontmatter must parse to a mapping"
        assert frontmatter.get("name"), f"{path} frontmatter must include name"
        assert frontmatter.get("description"), f"{path} frontmatter must include description"
