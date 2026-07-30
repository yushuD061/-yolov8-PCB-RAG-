"""
告警 SQLite 存储 — 去重缓存 + 持久化 + 查询/清空。
PCB 缺陷检测：简化告警记录，无交通相关字段。
"""

import re
import time
from models import AlarmRecord
from store.base import BaseStore, AlarmStats

_ALARMS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS alarms (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    target_id INTEGER NOT NULL,
    type TEXT NOT NULL,
    message TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alarms_time ON alarms (timestamp DESC);
"""


class AlarmStore(BaseStore):
    def __init__(self, db_path: str | None = None):
        super().__init__(db_path=db_path, table_sql=_ALARMS_TABLE_SQL)
        self._dedup_cache: dict[int, float] = {}
        self._migrated = False

    def _ensure_migrated(self):
        """惰性迁移：在首次写入前检查并删除旧的 speed 列。"""
        if self._migrated or self._conn is None:
            return
        self._migrated = True
        try:
            cursor = self._conn.execute("PRAGMA table_info(alarms)")
            cols = {row[1] for row in cursor.fetchall()}
            if "speed" in cols:
                self._conn.executescript("""
                    CREATE TABLE alarms_new (
                        id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        target_id INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        message TEXT NOT NULL
                    );
                    INSERT INTO alarms_new SELECT id, timestamp, target_id, type, message FROM alarms;
                    DROP TABLE alarms;
                    ALTER TABLE alarms_new RENAME TO alarms;
                    CREATE INDEX IF NOT EXISTS idx_alarms_time ON alarms (timestamp DESC);
                """)
                self._conn.commit()
                print("[AlarmStore] 迁移完成：已删除旧的 speed 列")
        except Exception as e:
            print(f"[AlarmStore] 迁移跳过: {e}")

    def append(self, alarm: AlarmRecord):
        """追加告警记录（同一 target 30 秒内不重复）"""
        self._ensure_migrated()
        """追加告警记录（同一 target 30 秒内不重复）"""
        now = time.time()
        if alarm.targetId in self._dedup_cache:
            if now - self._dedup_cache[alarm.targetId] < 30:
                return
        self._dedup_cache[alarm.targetId] = now

        if self._conn is None:
            return
        self._conn.execute("""
            INSERT OR REPLACE INTO alarms
            (id, timestamp, target_id, type, message)
            VALUES (?, ?, ?, ?, ?)
        """, (alarm.id, alarm.timestamp, alarm.targetId, alarm.type, alarm.message))
        self._conn.commit()

        self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if now - v < 30}

    def list(self, limit: int = 100) -> list[AlarmRecord]:
        if self._conn is None:
            return []
        cursor = self._conn.execute(
            "SELECT * FROM alarms ORDER BY timestamp DESC LIMIT ?", (limit,))
        results = []
        for row in cursor.fetchall():
            results.append(AlarmRecord(
                id=row[0], timestamp=row[1], targetId=row[2],
                type=row[3], message=row[4],
            ))
        return results

    def clear(self):
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM alarms")
        self._conn.commit()
        self._dedup_cache.clear()

    def prune(self, retention_days: int) -> int:
        """删除早于保留期的缺陷明细。"""
        if self._conn is None:
            return 0
        cursor = self._conn.execute(
            "DELETE FROM alarms WHERE datetime(timestamp) < datetime('now', ?)",
            (f"-{max(1, retention_days)} days",),
        )
        self._conn.commit()
        return max(0, cursor.rowcount)

    def stats(self) -> AlarmStats:
        """检测统计：按缺陷类型计数 + 总计 + 时间范围"""
        if self._conn is None:
            return AlarmStats()
        rows = self._conn.execute(
            "SELECT message, timestamp FROM alarms ORDER BY timestamp"
        ).fetchall()
        total = len(rows)
        by_type: dict[str, int] = {}
        for msg, _ in rows:
            # message 格式: "检测到 漏孔 缺陷，置信度 85.3%"
            m = re.search(r'检测到\s*(\S+)\s*缺陷', msg)
            name = m.group(1) if m else "未知"
            by_type[name] = by_type.get(name, 0) + 1
        return AlarmStats(
            total=total,
            by_type=by_type,
            first_at=rows[0][1] if rows else None,
            last_at=rows[-1][1] if rows else None,
        )
