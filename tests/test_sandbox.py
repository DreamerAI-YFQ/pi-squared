from pi_agent.extensions.sandbox import LocalSandbox


def test_sandbox_isolates_files(tmp_path):
    import os

    sandbox = LocalSandbox()
    # 在沙箱里写文件，文件落在沙箱临时目录里（而非宿主 cwd）
    result = sandbox.exec("echo hello > out.txt")
    assert result.ok
    assert os.path.exists(os.path.join(sandbox.directory, "out.txt"))


def test_sandbox_directory_is_tmp():
    sandbox = LocalSandbox()
    assert "pi-sandbox-" in sandbox.directory


def test_sandbox_exec_result():
    sandbox = LocalSandbox()
    result = sandbox.exec("echo hi")
    assert result.ok
    assert result.value.exit_code == 0
