from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.skills import load_skills, parse_frontmatter


def test_parse_frontmatter():
    content = "---\nname: pdf\ndescription: 处理 PDF\n---\n这是正文"
    fm, body = parse_frontmatter(content)
    assert fm["name"] == "pdf"
    assert fm["description"] == "处理 PDF"
    assert body == "这是正文"


def test_load_skills(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.create_dir("skills/pdf")
    env.write_file(
        "skills/pdf/SKILL.md",
        "---\nname: pdf\ndescription: 处理 PDF 文件\n---\n# PDF 处理\n用工具处理 PDF",
    )
    env.create_dir("skills/note")
    env.write_file(
        "skills/note/SKILL.md",
        "---\ndescription: 记笔记\n---\n记笔记的方法",
    )

    skills = load_skills(env, ["skills"])
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"pdf", "note"}


def test_load_skills_skips_missing_description(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.create_dir("skills/bad")
    env.write_file("skills/bad/SKILL.md", "没有 frontmatter 的正文")

    skills = load_skills(env, ["skills"])
    assert skills == []
