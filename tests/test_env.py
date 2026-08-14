from pi_agent.harness.env import LocalExecutionEnv
from pi_agent.harness.result import is_err, is_ok


def test_write_and_read(tmp_path):
    env = LocalExecutionEnv(cwd=str(tmp_path))
    assert is_ok(env.write_file("a.txt", "hello"))
    r = env.read_text_file("a.txt")
    assert is_ok(r)
    assert r.value == "hello"


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
