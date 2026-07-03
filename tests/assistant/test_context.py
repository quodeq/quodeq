from quodeq.assistant._context import build_system_prompt, build_turn_message
from quodeq.assistant.skills import load_skills


def test_system_prompt_contains_identity_and_rules():
    prompt = build_system_prompt()
    assert "quodeq" in prompt.lower()
    assert "UNTRUSTED DATA" in prompt  # fenced-data rule stated up front
    assert "draft_action" in prompt


def test_system_prompt_with_skill_appends_instructions():
    skill = load_skills()["create-standard"]
    prompt = build_system_prompt(skill=skill)
    assert prompt.endswith(skill.instructions) or skill.instructions in prompt


def test_turn_message_serializes_ui_state():
    msg = build_turn_message("why grade C?", {"activeTab": "overview", "selectedRun": "r1"})
    assert msg.startswith("[ui-state]")
    assert '"activeTab": "overview"' in msg
    assert msg.endswith("why grade C?")


def test_turn_message_without_ui_state():
    assert build_turn_message("hello", None) == "hello"
