import os
import shutil
import stat as stat_module
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pi_agent.harness.result import Result, err, ok

FileKind = Literal["file", "directory", "other"]


@dataclass
class FileInfo:
    """文件元数据（对应 pi 的 FileInfo）。"""
    name: str
    path: str
    kind: FileKind
    size: int
    mtime_ms: int


@dataclass
class ShellResult:
    """shell 执行结果（对应 pi 的 Shell.exec 返回值）。"""
    stdout: str
    stderr: str
    exit_code: int


class FileSystem(Protocol):
    """文件系统能力（对应 pi 的 FileSystem）。

    核心不变式：方法绝不抛异常，所有失败都编码进返回的 Result。
    """
    cwd: str

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
    """shell 执行能力（对应 pi 的 Shell）。"""
    def exec(self, command: str, cwd: str | None = None, timeout: float | None = None) -> Result: ...


class ExecutionEnv(FileSystem, Shell, Protocol):
    """文件系统 + 进程执行环境（对应 pi 的 ExecutionEnv）。"""


class LocalExecutionEnv:
    """本地实现：用 os / pathlib / subprocess（对应 pi 的 env/nodejs.ts）。"""

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd or os.getcwd()

    def _resolve(self, path: str) -> str:
        p = Path(path)
        if not p.is_absolute():
            p = Path(self.cwd) / p
        return str(p)

    def absolute_path(self, path: str) -> Result:
        try:
            return ok(self._resolve(path))
        except Exception as exc:
            return err(exc)

    def join_path(self, parts: list[str]) -> Result:
        try:
            return ok(str(Path(*parts)))
        except Exception as exc:
            return err(exc)

    def read_text_file(self, path: str) -> Result:
        try:
            with open(self._resolve(path), encoding="utf-8") as f:
                return ok(f.read())
        except Exception as exc:
            return err(exc)

    def write_file(self, path: str, content: str) -> Result:
        try:
            p = Path(self._resolve(path))
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ok(None)
        except Exception as exc:
            return err(exc)

    def file_info(self, path: str) -> Result:
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
        try:
            return ok(str(Path(self._resolve(path)).resolve()))
        except Exception as exc:
            return err(exc)

    def exists(self, path: str) -> Result:
        try:
            return ok(Path(self._resolve(path)).exists())
        except Exception as exc:
            return err(exc)

    def create_dir(self, path: str) -> Result:
        try:
            Path(self._resolve(path)).mkdir(parents=True, exist_ok=True)
            return ok(None)
        except Exception as exc:
            return err(exc)

    def remove(self, path: str) -> Result:
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
        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=cwd or self.cwd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ok(
                ShellResult(
                    stdout=result.stdout,
                    stderr=result.stderr,
                    exit_code=result.returncode,
                )
            )
        except Exception as exc:
            return err(exc)
