import re
from dataclasses import dataclass

from pi_agent.harness.env import ExecutionEnv
from pi_agent.harness.skills import parse_frontmatter


@dataclass
class PromptTemplate:
    name: str
    content: str
    description: str = ""


def _arg(args: list[str], index: int) -> str:
    """取第 index 个参数（1-based），越界返回空串。"""
    i = index - 1
    return args[i] if 0 <= i < len(args) else ""


def substitute_args(content: str, args: list[str]) -> str:
    """替换占位符（$1、$@、$ARGUMENTS、${@:N}、${@:N:L}）。

    顺序关键：先位置参数 $1，再切片 ${@:N}，最后 $@ / $ARGUMENTS，
    避免 $@ 误伤 ${@:N}，也避免 $1 误读成 $10 的前缀。
    """
    result = content

    # 1. 位置参数 $1 $2 ...（1-based），用正则精确匹配避免 $10 误读
    result = re.sub(r"\$(\d+)", lambda m: _arg(args, int(m.group(1))), result)

    # 2. 切片 ${@:N} / ${@:N:L}（N 是 1-based）
    def slice_repl(m: re.Match) -> str:
        start = int(m.group(1)) - 1
        if start < 0:
            start = 0
        if m.group(2):
            return " ".join(args[start : start + int(m.group(2))])
        return " ".join(args[start:])

    result = re.sub(r"\$\{@:(\d+)(?::(\d+))?\}", slice_repl, result)

    # 3. $ARGUMENTS 和 $@（所有参数拼接）
    all_args = " ".join(args)
    result = result.replace("$ARGUMENTS", all_args)
    result = result.replace("$@", all_args)

    return result


def parse_command_args(args_string: str) -> list[str]:
    """解析 shell 风格的参数字符串，处理单/双引号。

    例如 'a.py "带 空格"' -> ['a.py', '带 空格']
    """
    args: list[str] = []
    current = ""
    in_quote: str | None = None

    for char in args_string:
        if in_quote:
            if char == in_quote:
                in_quote = None
            else:
                current += char
        elif char in ('"', "'"):
            in_quote = char
        elif char in (" ", "\t"):
            if current:
                args.append(current)
                current = ""
        else:
            current += char

    if current:
        args.append(current)
    return args


def format_prompt_template_invocation(template: PromptTemplate, args: list[str] | None = None) -> str:
    """把模板 + 参数组合成最终 prompt。"""
    return substitute_args(template.content, args or [])


def prompt_template_from_md(content: str, file_path: str = "") -> PromptTemplate | None:
    """从 markdown（frontmatter + body）解析出一个 prompt 模板。"""
    frontmatter, body = parse_frontmatter(content)
    name = frontmatter.get("name")
    if not name:
        return None
    return PromptTemplate(
        name=name,
        content=body,
        description=frontmatter.get("description", ""),
    )


def load_prompt_templates(env: ExecutionEnv, dir_path: str) -> list[PromptTemplate]:
    """从目录加载所有 .md 文件作为 prompt 模板。"""
    templates: list[PromptTemplate] = []
    entries = env.list_dir(dir_path)
    if not entries.ok:
        return templates
    for entry in entries.value:
        if entry.kind != "file" or not entry.name.endswith(".md"):
            continue
        content = env.read_text_file(entry.path)
        if not content.ok:
            continue
        template = prompt_template_from_md(content.value, entry.path)
        if template:
            templates.append(template)
    return templates
