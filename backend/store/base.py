"""
存储层数据结构 + 基类 — 集中定义 SQLite store 的返回类型与公共连接逻辑。
"""

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta


# ═══════════════════ 数据结构 ═══════════════════

@dataclass
class AlarmStats:
    """告警检测统计（按缺陷类型计数）。"""
    total: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    first_at: str | None = None
    last_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "by_type": self.by_type,
            "first_at": self.first_at,
            "last_at": self.last_at,
        }


@dataclass
class DailyStat:
    """单日检测数统计。"""
    date: str
    total_detections: int = 0

    def to_dict(self) -> dict:
        return {"date": self.date, "totalDetections": self.total_detections}


# ═══════════════════ BaseStore ═══════════════════

_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "alarms.db"
)


class BaseStore:
    """SQLite 持久化基类：统一连接 / 路径 / 关闭。"""

    def __init__(self, db_path: str | None = None, table_sql: str = ""):
        self._db_path = os.path.abspath(db_path or _DEFAULT_DB_PATH)
        self._table_sql = table_sql
        self._conn: sqlite3.Connection | None = None

    @property
    def db_path(self) -> str:
        return self._db_path

    def connect(self):
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        if self._table_sql:
            self._conn.executescript(self._table_sql)
            self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection | None:
        return self._conn