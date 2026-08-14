from pi_agent.harness.system_prompt import Skill, format_skills_for_system_prompt


def test_format_skills_filters_disabled():
    skills = [
        Skill(name="pdf", description="处理 PDF", content="..."),
        Skill(name="add-provider", description="添加 provider", content="...", disable_model_invocation=True),
    ]
    result = format_skills_for_system_prompt(skills)
    assert "pdf" in result
    assert "add-provider" not in result
    assert "<available_skills>" in result
    assert "</available_skills>" in result


def test_xml_escape():
    skills = [Skill(name="a<b", description='c&d"e', content="...")]
    result = format_skills_for_system_prompt(skills)
    assert "a&lt;b" in result
    assert "c&amp;d&quot;e" in result


def test_empty_skills():
    assert format_skills_for_system_prompt([]) == ""
    assert format_skills_for_system_prompt([Skill(name="x", description="y", content="", disable_model_invocation=True)]) == ""
