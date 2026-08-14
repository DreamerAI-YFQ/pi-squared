from pi_agent.harness.env import LocalExecutionEnv, decode_output
from pi_agent.harness.result import is_err, is_ok


def test_write_and_read(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    assert is_ok(env.write_file("a.txt", "hello"))
    r = env.read_text_file("a.txt")
    assert is_ok(r)
    assert r.value == "hello"


def test_decode_output_multibyte_fallback():
    """子进程输出解码：UTF-8 直读，GBK 回退，非法字节替换（不抛异常）。

    Windows 中文系统 subprocess 默认按 locale(GBK) 解码，
    遇到 UTF-8 输出（如 git 中文文件名）曾直接 UnicodeDecodeError。
    """
    assert decode_output("世界".encode("utf-8")) == "世界"
    assert decode_output("世界".encode("gbk")) == "世界"
    # 0x8e 等非法序列：替换而非崩溃
    out = decode_output(b"\x8e\xff\xfe")
    assert isinstance(out, str)


def test_exec_non_ascii_output(tmp_path):
    """exec 输出含中文时不崩，且内容可读（回归：GBK 解码崩溃）。"""
    env = LocalExecutionEnv(cwd=str(tmp_path))
    r = env.exec('python -c "print(\'世界\')"')
    assert is_ok(r)
    assert "世界" in r.value.stdout


def test_file_info(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "hello")
    info = env.file_info("a.txt")
    assert is_ok(info)
    assert info.value.name == "a.txt"
    assert info.value.kind == "file"
    assert info.value.size == 5


def test_list_dir(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    env.write_file("a.txt", "x")
    env.write_file("b.txt", "y")
    r = env.list_dir(".")
    assert is_ok(r)
    assert len(r.value) == 2


def test_exists_and_create_dir(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    assert env.exists("sub").value is False
    env.create_dir("sub")
    assert env.exists("sub").value is True


def test_exec(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    r = env.exec("echo hello")
    assert is_ok(r)
    assert r.value.exit_code == 0
    assert "hello" in r.value.stdout


def test_read_nonexistent_returns_err(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    r = env.read_text_file("nope.txt")
    assert is_err(r)
