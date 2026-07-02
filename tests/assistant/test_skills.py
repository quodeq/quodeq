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
