from pi_agent.harness.prompt_templates import (
    PromptTemplate,
    format_prompt_template_invocation,
    parse_command_args,
    substitute_args,
)


def test_positional():
    assert substitute_args("读 $1 的第 $2 行", ["a.txt", "10"]) == "读 a.txt 的第 10 行"


def test_all_args():
    assert substitute_args("参数: $@", ["a", "b", "c"]) == "参数: a b c"


def test_arguments_keyword():
    assert substitute_args("参数: $ARGUMENTS", ["a", "b"]) == "参数: a b"


def test_slice_from_n():
    # ${@:2} 从第 2 个参数开始（1-based）
    assert substitute_args("从第2个起: ${@:2}", ["a", "b", "c"]) == "从第2个起: b c"


def test_slice_with_length():
    assert substitute_args("取2个: ${@:1:2}", ["a", "b", "c"]) == "取2个: a b"


def test_out_of_range_returns_empty():
    assert substitute_args("$1|$2", ["a"]) == "a|"


def test_double_digit_positional():
    args = [str(i) for i in range(10)]
    assert substitute_args("$10", args) == "9"


def test_parse_simple():
    assert parse_command_args("a.py 性能") == ["a.py", "性能"]


def test_parse_with_quotes():
    assert parse_command_args('a.py "带 空格"') == ["a.py", "带 空格"]


def test_parse_single_quotes():
    assert parse_command_args("'单引号 内容'") == ["单引号 内容"]


def test_parse_empty_and_tabs():
    assert parse_command_args("") == []
    assert parse_command_args("a\tb") == ["a", "b"]


def test_format_invocation():
    template = PromptTemplate(name="analyze", content="分析 $1，重点 $2")
    assert format_prompt_template_invocation(template, ["a.py", "性能"]) == "分析 a.py，重点 性能"
