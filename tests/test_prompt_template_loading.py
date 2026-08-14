from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.prompt_templates import load_prompt_templates, prompt_template_from_md


MD = """---
name: create_file
description: 创建文件
---
创建文件 $1，内容：$2
"""


def test_prompt_template_from_md():
    tpl = prompt_template_from_md(MD)
    assert tpl.name == "create_file"
    assert tpl.description == "创建文件"
    assert "创建文件 $1" in tpl.content


def test_load_prompt_templates_from_dir(tmp_path):
    (tmp_path / "create.md").write_text(MD, encoding="utf-8")
    (tmp_path / "notes.txt").write_text("plain", encoding="utf-8")  # 非 .md，应忽略

    env = LocalExecutionEnv(cwd=str(tmp_path))
    templates = load_prompt_templates(env, ".")

    assert [t.name for t in templates] == ["create_file"]
