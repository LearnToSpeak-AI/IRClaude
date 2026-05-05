from __future__ import annotations

import signal
from typing import Sequence

import pexpect


class PtySession:
    """Thin wrapper around pexpect.spawn for one PTY-managed subprocess."""

    def __init__(self, argv: Sequence[str], cwd: str, env: dict[str, str] | None = None):
        self.argv = list(argv)
        self.cwd = cwd
        self.env = env
        self._proc: pexpect.spawn | None = None

    def spawn(self) -> None:
        self._proc = pexpect.spawn(
            self.argv[0], args=self.argv[1:], cwd=self.cwd, env=self.env,
            encoding="utf-8", timeout=None, dimensions=(40, 120),
        )

    def write(self, data: str) -> None:
        if self._proc is None:
            raise RuntimeError("not spawned")
        self._proc.send(data)

    def read_nonblocking(self, timeout: float = 0.1) -> str:
        if self._proc is None:
            return ""
        try:
            return self._proc.read_nonblocking(size=4096, timeout=timeout)
        except pexpect.TIMEOUT:
            return ""
        except pexpect.EOF:
            return ""

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.isalive()

    def terminate(self) -> None:
        if self._proc is None:
            return
        try:
            self._proc.kill(signal.SIGTERM)
            self._proc.wait()
        except Exception:
            try:
                self._proc.kill(signal.SIGKILL)
            except Exception:
                pass
