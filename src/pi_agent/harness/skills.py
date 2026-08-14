"""技能加载（对应 pi 的 skills.ts 简化版）。

从目录读取 SKILL.md，解析 frontmatter（name/description），返回 Skill 列表。
"""
from pi_agent.harness.env import ExecutionEnv
from pi_agent.harness.system_prompt import Skill


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """解析 markdown frontmatter，返回 (frontmatter 字典, body 文本)。"""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if not normalized.startswith("---"):
        return {}, normalized
    end = normalized.find("\n---", 3)
    if end == -1:
        return {}, normalized
    yaml_str = normalized[4:end]  # 跳过开头的 "---\n"
    body = normalized[end + 4:].strip()
    return _parse_simple_yaml(yaml_str), body


def _parse_simple_yaml(text: str) -> dict:
    """解析简单的 key: value YAML（不依赖 yaml 库，够 skill frontmatter 用）。"""
    result: dict = {}
    for line in text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, _, value = line.partition(":")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _skill_from_md(content: str, dir_name: str, file_path: str) -> Skill | None:
    frontmatter, body = parse_frontmatter(content)
    name = frontmatter.get("name") or dir_name
    description = frontmatter.get("description")
    if not description:
        return None  # description 必填，否则跳过
    disable = frontmatter.get("disable-model-invocation") == "true"
    return Skill(
        name=name,
        description=description,
        content=body,
        file_path=file_path,
        disable_model_invocation=disable,
    )


def load_skills(env: ExecutionEnv, dirs: list[str]) -> list[Skill]:
    """从目录加载技能：每个子目录里的 SKILL.md 是一个技能。"""
    skills: list[Skill] = []
    for dir_path in dirs:
        entries = env.list_dir(dir_path)
        if not entries.ok:
            continue
        for entry in entries.value:
            if entry.kind != "directory":
                continue
            skill_md = env.read_text_file(f"{entry.path}/SKILL.md")
            if not skill_md.ok:
                continue
            skill = _skill_from_md(skill_md.value, entry.name, entry.path)
            if skill:
                skills.append(skill)
    return skills
