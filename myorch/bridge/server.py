import asyncio
import os
import signal
from pathlib import Path


class ErgoServer:
    """Manage an ergo subprocess: start, stop (graceful then SIGKILL), is_running."""

    def __init__(
        self,
        binary_path: Path,
        config_path: Path,
        *,
        kill_after: float = 5.0,
    ):
        self._binary = Path(binary_path)
        self._config = Path(config_path)
        self._kill_after = kill_after
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    @property
    def pid(self) -> int | None:
        return self._proc.pid if self._proc is not None else None

    async def start(self) -> None:
        if self.is_running:
            raise RuntimeError("ergo is already running")
        self._proc = await asyncio.create_subprocess_exec(
            str(self._binary),
            "run",
            "--conf",
            str(self._config),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=os.setsid,
        )

    async def stop(self) -> None:
        proc = self._proc
        if proc is None or proc.returncode is not None:
            self._proc = None
            return

        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            self._proc = None
            return

        try:
            await asyncio.wait_for(proc.wait(), timeout=self._kill_after)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()
        self._proc = None
