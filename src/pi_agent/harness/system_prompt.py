from dataclasses import dataclass


@dataclass
class Skill:
    """技能：一段按需注入的指令（对应 pi 的 harness/types.ts 的 Skill）。"""
    name: str
    description: str
    content: str
    file_path: str = ""
    disable_model_invocation: bool = False


def _xml_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def format_skills_for_system_prompt(skills: list[Skill]) -> str:
    """把技能列表格式化成系统提示中的 <available_skills> XML 块。

    - disable_model_invocation=True 的技能不放进目录（只允许显式调用）
    - name/description 做 XML 转义，避免破坏 XML
    """
    visible = [s for s in skills if not s.disable_model_invocation]
    if not visible:
        return ""

    lines = ["<available_skills>"]
    for skill in visible:
        name = _xml_escape(skill.name)
        description = _xml_escape(skill.description)
        lines.append(f'  <skill name="{name}" description="{description}" />')
    lines.append("</available_skills>")
    return "\n".join(lines)
