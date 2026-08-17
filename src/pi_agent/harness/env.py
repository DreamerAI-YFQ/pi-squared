"""
执行环境抽象层：文件系统 + Shell 执行能力。

对应 pi 的 env/nodejs.ts。定义了 Agent 需要的所有环境操作：
- 文件系统：读写文件、列出目录、创建/删除文件、获取文件信息等
- Shell 执行：运行命令并获取 stdout/stderr/exit_code

核心设计：
1. 通过 Protocol 定义接口（FileSystem、Shell、ExecutionEnv）
2. 通过具体实现（LocalExecutionEnv）提供能力
3. 所有方法都返回 Result 类型，绝不抛异常
4. 支持多种实现（本地、容器、远程等）

使用场景：
- Agent 需要读取/写入代码文件
- Agent 需要执行 shell 命令（如 git、npm、pytest）
- Agent 需要检查文件/目录是否存在
- Agent 需要获取文件元数据（大小、修改时间）
"""
import os
import shutil
import stat as stat_module
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pi_agent.harness.result import Result, err, ok

# 文件类型：文件、目录、其他（如符号链接、设备文件等）
FileKind = Literal["file", "directory", "other"]


def decode_output(data: bytes) -> str:
    """解码子进程输出：UTF-8 → GBK → 替换。

    Windows 上 subprocess 默认用 locale（中文系统是 GBK）解码，
    遇到 UTF-8 输出（如 git/ls 的中文文件名）会直接 UnicodeDecodeError。
    因此一律按 bytes 读取，再按常见编码回退解码。

    Args:
        data: 子进程返回的原始字节

    Returns:
        解码后的字符串，如果所有编码都失败则用 UTF-8 替换模式
    """
    for enc in ("utf-8", "gbk"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@dataclass
class FileInfo:
    """文件元数据（对应 pi 的 FileInfo）。

    用于 Agent 了解文件的基本信息，判断是否需要读取或修改。
    """
    name: str  # 文件名（不含路径）
    path: str  # 完整路径
    kind: FileKind  # 文件类型：file/directory/other
    size: int  # 文件大小（字节）
    mtime_ms: int  # 修改时间（毫秒）


@dataclass
class ShellResult:
    """shell 执行结果（对应 pi 的 Shell.exec 返回值）。

    用于 Agent 获取命令执行的完整输出和状态。
    """
    stdout: str  # 标准输出
    stderr: str  # 标准错误
    exit_code: int  # 退出码（0 表示成功）


class FileSystem(Protocol):
    """文件系统能力（对应 pi 的 FileSystem）。

    定义了 Agent 需要的所有文件系统操作。

    核心不变式：方法绝不抛异常，所有失败都编码进返回的 Result。
    这确保 Agent 可以安全地处理错误，而不是让异常传播到外部。
    """
    cwd: str  # 当前工作目录

    def absolute_path(self, path: str) -> Result: ...
    def join_path(self, parts: list[str]) -> Result: ...
    def read_text_file(self, path: str) -> Result: ...
    def write_file(self, path: str, content: str) -> Result: ...
    def file_info(self, path: str) -> Result: ...
    def list_dir(self, path: str) -> Result: ...
    def canonical_path(self, path: str) -> Result: ...
    def exists(self, path: str) -> Result: ...
    def create_dir(self, path: str) -> Result: ...
    def remove(self, path: str) -> Result: ...


class Shell(Protocol):
    """shell 执行能力（对应 pi 的 Shell）。

    定义了 Agent 执行命令的接口。
    """
    def exec(self, command: str, cwd: str | None = None, timeout: float | None = None) -> Result: ...


class ExecutionEnv(FileSystem, Shell, Protocol):
    """文件系统 + 进程执行环境（对应 pi 的 ExecutionEnv）。

    这是 Agent 的完整环境接口，组合了文件系统和 Shell 能力。
    """


class LocalExecutionEnv:
    """本地实现：用 os / pathlib / subprocess（对应 pi 的 env/nodejs.ts）。

    这是最常用的实现，直接在本地文件系统和进程中执行操作。
    可以替换成其他实现（如 Docker 容器、远程 SSH 等）。
    """

    def __init__(self, cwd: str | None = None):
        """初始化本地执行环境。

        Args:
            cwd: 初始工作目录，默认为当前进程的工作目录
        """
        self.cwd = cwd or os.getcwd()

    def _resolve(self, path: str) -> str:
        """解析相对路径为绝对路径。

        Args:
            path: 相对路径或绝对路径

        Returns:
            绝对路径字符串
        """
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.cwd) / p
        return str(p)

    def absolute_path(self, path: str) -> Result:
        """获取绝对路径。

        Args:
            path: 相对路径或绝对路径

        Returns:
            Result[str, Exception]：成功返回绝对路径，失败返回异常
        """
        try:
            return ok(self._resolve(path))
        except Exception as exc:
            return err(exc)

    def join_path(self, parts: list[str]) -> Result:
        """拼接路径片段。

        Args:
            parts: 路径片段列表（如 ["src", "components", "file.ts"]）

        Returns:
            Result[str, Exception]：成功返回拼接后的路径，失败返回异常
        """
        try:
            return ok(str(Path(*parts)))
        except Exception as exc:
            return err(exc)

    def read_text_file(self, path: str) -> Result:
        """读取文本文件。

        Args:
            path: 文件路径

        Returns:
            Result[str, Exception]：成功返回文件内容，失败返回异常
        """
        try:
            with open(self._resolve(path), encoding="utf-8") as f:
                return ok(f.read())
        except Exception as exc:
            return err(exc)

    def write_file(self, path: str, content: str) -> Result:
        """写入文件（自动创建父目录）。

        Args:
            path: 文件路径
            content: 文件内容

        Returns:
            Result[None, Exception]：成功返回 None，失败返回异常
        """
        try:
            p = Path(self._resolve(path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ok(None)
        except Exception as exc:
            return err(exc)

    def file_info(self, path: str) -> Result:
        """获取文件元数据。

        Args:
            path: 文件路径

        Returns:
            Result[FileInfo, Exception]：成功返回文件信息，失败返回异常
        """
        try:
            p = Path(self._resolve(path))
            st = p.lstat()  # 不跟随 symlink
            if stat_module.S_ISDIR(st.st_mode):
                kind: FileKind = "directory"
            elif stat_module.S_ISREG(st.st_mode):
                kind = "file"
            else:
                kind = "other"
            return ok(
                FileInfo(
                    name=p.name,
                    path=str(p),
                    kind=kind,
                    size=st.st_size,
                    mtime_ms=int(st.st_mtime * 1000),
                )
            )
        except Exception as exc:
            return err(exc)

    def list_dir(self, path: str) -> Result:
        """列出目录内容。

        Args:
            path: 目录路径

        Returns:
            Result[list[FileInfo], Exception]：成功返回文件信息列表，失败返回异常
        """
        try:
            p = Path(self._resolve(path))
            entries = []
            for child in p.iterdir():
                info = self.file_info(str(child))
                if info.ok:
                    entries.append(info.value)
            return ok(entries)
        except Exception as exc:
            return err(exc)

    def canonical_path(self, path: str) -> Result:
        """获取规范路径（解析 .. 和 .）。

        Args:
            path: 路径

        Returns:
            Result[str, Exception]：成功返回规范路径，失败返回异常
        """
        try:
            return ok(str(Path(self._resolve(path)).resolve()))
        except Exception as exc:
            return err(exc)

    def exists(self, path: str) -> Result:
        """检查路径是否存在。

        Args:
            path: 路径

        Returns:
            Result[bool, Exception]：成功返回是否存在，失败返回异常
        """
        try:
            return ok(Path(self._resolve(path)).exists())
        except Exception as exc:
            return err(exc)

    def create_dir(self, path: str) -> Result:
        """创建目录（自动创建父目录）。

        Args:
            path: 目录路径

        Returns:
            Result[None, Exception]：成功返回 None，失败返回异常
        """
        try:
            Path(self._resolve(path)).mkdir(parents=True, exist_ok=True)
            return ok(None)
        except Exception as exc:
            return err(exc)

    def remove(self, path: str) -> Result:
        """删除文件或目录（递归删除目录）。

        Args:
            path: 文件或目录路径

        Returns:
            Result[None, Exception]：成功返回 None，失败返回异常
        """
        try:
            p = Path(self._resolve(path))
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink(missing_ok=True)
            return ok(None)
        except Exception as exc:
            return err(exc)

    def exec(self, command: str, cwd: str | None = None, timeout: float | None = None) -> Result:
        """执行 shell 命令。

        Args:
            command: 要执行的命令（字符串，会通过 shell=True 传给 subprocess）
            cwd: 工作目录，默认为环境的工作目录
            timeout: 超时时间（秒），超时则抛异常

        Returns:
            Result[ShellResult, Exception]：成功返回命令执行结果，失败返回异常
        """
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or self.cwd,
                capture_output=True,
                timeout=timeout,
            )
            return ok(
                ShellResult(
                    stdout=decode_output(result.stdout),
                    stderr=decode_output(result.stderr),
                    exit_code=result.returncode,
                )
            )
        except Exception as exc:
            return err(exc)
