from quodeq.assistant.skills import load_skills


def test_builtin_skills_load():
    skills = load_skills()
    assert {"create-standard", "explain-finding", "explain-score"} <= set(skills)
    cs = skills["create-standard"]
    assert cs.description
    assert "draft_action" in cs.instructions


def test_custom_skills_dir(tmp_path):
    (tmp_path / "my-skill.md").write_text(
        "---\nname: my-skill\ndescription: Test skill\n---\nDo the thing.\n"
    )
    skills = load_skills(skills_dir=tmp_path)
    assert skills["my-skill"].instructions.strip() == "Do the thing."


def test_malformed_skill_skipped(tmp_path):
    (tmp_path / "bad.md").write_text("no frontmatter here")
    assert load_skills(skills_dir=tmp_path) == {}


def test_frontmatter_extras_parsed(tmp_path):
    (tmp_path / "s.md").write_text(
        "---\nname: s\ndescription: D\nargument_hint: [dim]\n"
        "views: overview, violations\n---\nBody.\n"
    )
    skill = load_skills(skills_dir=tmp_path)["s"]
    assert skill.argument_hint == "[dim]"
    assert skill.views == ("overview", "violations")


def test_extras_default_empty(tmp_path):
    (tmp_path / "s.md").write_text("---\nname: s\ndescription: D\n---\nBody.\n")
    skill = load_skills(skills_dir=tmp_path)["s"]
    assert skill.argument_hint == ""
    assert skill.views == ()


def test_reserved_command_name_skipped(tmp_path):
    (tmp_path / "help.md").write_text("---\nname: help\ndescription: D\n---\nBody.\n")
    assert load_skills(skills_dir=tmp_path) == {}
