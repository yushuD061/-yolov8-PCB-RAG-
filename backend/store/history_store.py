"""
检测记录统计 — 每天汇总缺陷检测次数。
"""

from datetime import datetime, timedelta
from store.base import BaseStore, DailyStat

_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS daily_stats (
    date TEXT PRIMARY KEY,
    total_detections INTEGER DEFAULT 0
);
"""


class HistoryStore(BaseStore):
    def __init__(self, db_path: str | None = None):
        super().__init__(db_path=db_path, table_sql=_HISTORY_TABLE_SQL)

    def accumulate(self, detections: int = 0):
        """累加当日检测数"""
        if self._conn is None:
            return
        today = datetime.now().strftime("%m-%d")
        self._conn.execute("""
            INSERT INTO daily_stats (date, total_detections)
            VALUES (?, ?)
            ON CONFLICT(date) DO UPDATE SET
                total_detections = total_detections + ?
        """, (today, detections, detections))
        self._conn.commit()

    def get_7days(self) -> list[DailyStat]:
        """返回最近 7 天的统计"""
        if self._conn is None:
            return []
        results: list[DailyStat] = []
        for i in range(6, -1, -1):
            day = (datetime.now() - timedelta(days=i)).strftime("%m-%d")
            cursor = self._conn.execute(
                "SELECT total_detections FROM daily_stats WHERE date = ?", (day,))
            row = cursor.fetchone()
            results.append(DailyStat(
                date=day,
                total_detections=row[0] if row else 0,
            ))
        return results