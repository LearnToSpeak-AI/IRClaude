import os
import signal
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from threading import Lock


class RingBuffer:
    def __init__(self, capacity: int):
        self._dq: deque[str] = deque(maxlen=capacity)
        self._lock = Lock()

    def append(self, line: str) -> None:
        with self._lock:
            self._dq.append(line)

    def tail(self) -> list[str]:
        with self._lock:
            return list(self._dq)

    def clear(self) -> None:
        with self._lock:
            self._dq.clear()


@dataclass
class _DevProc:
    popen: subprocess.Popen
    buffer: RingBuffer
    reader: threading.Thread


class DevServerManager:
    def __init__(self, buffer_capacity: int = 500):
        self._procs: dict[int, _DevProc] = {}
        self._buffer_capacity = buffer_capacity
        self._lock = threading.Lock()

    def start(self, project_id: int, command: str, cwd: str) -> None:
        with self._lock:
            self._stop_unlocked(project_id)
            buf = RingBuffer(capacity=self._buffer_capacity)
            popen = subprocess.Popen(
                command, cwd=cwd, shell=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                preexec_fn=os.setsid,
            )

            def reader():
                try:
                    assert popen.stdout is not None
                    for line in iter(popen.stdout.readline, ""):
                        if not line:
                            break
                        buf.append(line.rstrip("\n"))
                finally:
                    if popen.stdout:
                        popen.stdout.close()

            t = threading.Thread(target=reader, daemon=True)
            t.start()
            self._procs[project_id] = _DevProc(popen=popen, buffer=buf, reader=t)

    def stop(self, project_id: int) -> None:
        with self._lock:
            self._stop_unlocked(project_id)

    def _stop_unlocked(self, project_id: int) -> None:
        proc = self._procs.pop(project_id, None)
        if proc is None:
            return
        try:
            os.killpg(os.getpgid(proc.popen.pid), signal.SIGTERM)
            proc.popen.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.popen.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass
        except ProcessLookupError:
            pass

    def is_running(self, project_id: int) -> bool:
        proc = self._procs.get(project_id)
        return proc is not None and proc.popen.poll() is None

    def tail(self, project_id: int) -> list[str]:
        proc = self._procs.get(project_id)
        return proc.buffer.tail() if proc else []

    def shutdown_all(self) -> None:
        with self._lock:
            for pid in list(self._procs.keys()):
                self._stop_unlocked(pid)
