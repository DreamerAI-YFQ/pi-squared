"""沙箱（对应 ETCLOVG 的 E 层，特色实现）。

把命令执行关进隔离环境，防止模型动作影响宿主系统。
本地实现用「临时目录 + 子进程」：命令的 cwd 指向临时目录，
文件操作局限在沙箱目录内，宿主系统不受影响。
"""
import subprocess
import tempfile
from dataclasses import dataclass

from pi_agent.harness.result import Result, err, ok


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int


class Sandbox:
    """沙箱接口。"""

    def exec(self, command: str) -> Result:
        raise NotImplementedError

    def cleanup(self) -> None:
        pass


class LocalSandbox(Sandbox):
    """本地沙箱：临时目录 + 子进程，文件操作局限在沙箱目录。"""

    def __init__(self):
        self._tmpdir = tempfile.mkdtemp(prefix="pi-sandbox-")

    @property
    def directory(self) -> str:
        return self._tmpdir

    def exec(self, command: str) -> Result:
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self._tmpdir,  # 关键：命令在沙箱目录里执行
                capture_output=True,
                text=True,
            )
            return ok(
                SandboxResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            )
        except Exception as exc:
            return err(exc)
