"""
线程安全环形缓冲区 — 固定容量，先进先出，支持读取最新元素。
"""

import threading
from typing import Any


class RingBuffer:
    def __init__(self, capacity: int = 8):
        self._capacity = capacity
        self._buffer: list[Any] = []
        self._lock = threading.Lock()

    def push(self, item: Any):
        """追加元素，超出容量时丢弃最旧元素"""
        with self._lock:
            self._buffer.append(item)
            if len(self._buffer) > self._capacity:
                self._buffer.pop(0)

    def latest(self) -> Any | None:
        """获取最新元素"""
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def get_all(self) -> list[Any]:
        """获取全部元素（从头到尾）"""
        with self._lock:
            return list(self._buffer)

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._buffer)
