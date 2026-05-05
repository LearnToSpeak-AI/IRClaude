from collections import deque
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
