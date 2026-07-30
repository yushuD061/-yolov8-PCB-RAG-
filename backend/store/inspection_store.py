"""PCB 检测批次存储与质量统计。"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from store.base import BaseStore


_INSPECTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS inspections (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    item_name TEXT NOT NULL DEFAULT '',
    batch_id TEXT NOT NULL DEFAULT '',
    is_good INTEGER NOT NULL,
    defect_count INTEGER NOT NULL DEFAULT 0,
    defect_types TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_inspections_time
    ON inspections (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_inspections_quality
    ON inspections (is_good, source);
"""


@dataclass
class InspectionStats:
    total_inspected: int = 0
    good_count: int = 0
    defective_count: int = 0
    total_defects: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_source: dict[str, int] = field(default_factory=dict)
    first_at: str | None = None
    last_at: str | None = None

    @property
    def yield_rate(self) -> float | None:
        if self.total_inspected == 0:
            return None
        return self.good_count / self.total_inspected

    @property
    def defect_rate(self) -> float | None:
        if self.total_inspected == 0:
            return None
        return self.defective_count / self.total_inspected

    def to_dict(self) -> dict:
        return {
            "totalInspected": self.total_inspected,
            "goodCount": self.good_count,
            "defectiveCount": self.defective_count,
            "totalDefects": self.total_defects,
            "yieldRate": self.yield_rate,
            "yieldPercent": round(self.yield_rate * 100, 2) if self.yield_rate is not None else None,
            "defectRate": self.defect_rate,
            "defectPercent": round(self.defect_rate * 100, 2) if self.defect_rate is not None else None,
            "byType": self.by_type,
            "bySource": self.by_source,
            "firstAt": self.first_at,
            "lastAt": self.last_at,
        }


class InspectionStore(BaseStore):
    def __init__(self, db_path: str | None = None):
        super().__init__(db_path=db_path, table_sql=_INSPECTIONS_TABLE_SQL)

    def connect(self):
        super().connect()
        if self._conn is None:
            return
        columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(inspections)").fetchall()
        }
        if "batch_id" not in columns:
            self._conn.execute(
                "ALTER TABLE inspections ADD COLUMN batch_id TEXT NOT NULL DEFAULT ''"
            )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_inspections_batch ON inspections (batch_id)"
        )
        self._conn.commit()

    def append(
        self,
        detections: list[dict],
        source: str = "image",
        item_name: str = "",
        batch_id: str = "",
        timestamp: str | None = None,
        inspection_id: str | None = None,
    ) -> str:
        if self._conn is None:
            raise RuntimeError("检测历史数据库未连接")

        by_type: dict[str, int] = {}
        for detection in detections:
            name = str(detection.get("className") or "未知")
            by_type[name] = by_type.get(name, 0) + 1

        record_id = inspection_id or f"inspection-{uuid.uuid4().hex}"
        recorded_at = timestamp or datetime.now(timezone.utc).isoformat()
        defect_count = len(detections)
        self._conn.execute(
            """
            INSERT INTO inspections
                (id, timestamp, source, item_name, batch_id, is_good, defect_count, defect_types)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                recorded_at,
                source or "unknown",
                item_name or "",
                batch_id or "",
                1 if defect_count == 0 else 0,
                defect_count,
                json.dumps(by_type, ensure_ascii=False),
            ),
        )
        self._conn.commit()
        return record_id

    def stats(self) -> InspectionStats:
        if self._conn is None:
            return InspectionStats()
        rows = self._conn.execute(
            """
            SELECT timestamp, source, is_good, defect_count, defect_types
            FROM inspections ORDER BY timestamp
            """
        ).fetchall()
        result = InspectionStats(total_inspected=len(rows))
        for timestamp, source, is_good, defect_count, defect_types in rows:
            if is_good:
                result.good_count += 1
            else:
                result.defective_count += 1
            result.total_defects += int(defect_count or 0)
            result.by_source[source] = result.by_source.get(source, 0) + 1
            try:
                counts = json.loads(defect_types or "{}")
            except (TypeError, json.JSONDecodeError):
                counts = {}
            for name, count in counts.items():
                result.by_type[name] = result.by_type.get(name, 0) + int(count)
        if rows:
            result.first_at = rows[0][0]
            result.last_at = rows[-1][0]
        return result

    def recent(
        self,
        limit: int = 20,
        start_at: str | None = None,
        end_at: str | None = None,
        batch_id: str | None = None,
    ) -> list[dict]:
        if self._conn is None:
            return []
        conditions = []
        params: list[object] = []
        if start_at:
            conditions.append("timestamp >= ?")
            params.append(start_at)
        if end_at:
            conditions.append("timestamp <= ?")
            params.append(end_at)
        if batch_id:
            conditions.append("batch_id = ?")
            params.append(batch_id)
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(max(1, min(limit, 200)))
        rows = self._conn.execute(
            f"""
            SELECT id, timestamp, source, item_name, batch_id,
                   is_good, defect_count, defect_types
            FROM inspections {where} ORDER BY timestamp DESC LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            {
                "id": row[0],
                "timestamp": row[1],
                "source": row[2],
                "itemName": row[3],
                "batchId": row[4],
                "isGood": bool(row[5]),
                "defectCount": row[6],
                "defectTypes": json.loads(row[7] or "{}"),
            }
            for row in rows
        ]

    def clear(self) -> None:
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM inspections")
        self._conn.commit()

    def prune(self, retention_days: int) -> int:
        """删除早于保留期的检测批次。"""
        if self._conn is None:
            return 0
        cursor = self._conn.execute(
            "DELETE FROM inspections WHERE datetime(timestamp) < datetime('now', ?)",
            (f"-{max(1, retention_days)} days",),
        )
        self._conn.commit()
        return max(0, cursor.rowcount)
