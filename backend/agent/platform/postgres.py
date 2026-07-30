# postgres — PostgreSQL 平台客户端：连接、schema bootstrap、KG/RAG CRUD。
# 失败时降级到 mock（self._pool 为 None），不阻塞应用启动。
import json
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    _HAS_PG = True
except ImportError:
    psycopg2 = None  # type: ignore
    pg_pool = None   # type: ignore
    _HAS_PG = False


# ═══════════════════ DDL ═══════════════════

_DDLS: List[str] = [
    # RAG chunks
    """CREATE TABLE IF NOT EXISTS rag_chunks (
        id          BIGSERIAL PRIMARY KEY,
        doc_hash    TEXT NOT NULL,
        chunk_idx   INT NOT NULL,
        content     TEXT NOT NULL,
        embedding   JSONB,
        created_at  TIMESTAMP DEFAULT NOW(),
        UNIQUE(doc_hash, chunk_idx)
    )""",
    # RAG 文档元数据
    """CREATE TABLE IF NOT EXISTS rag_docs (
        doc_hash   TEXT PRIMARY KEY,
        doc_name   TEXT NOT NULL DEFAULT '',
        size       INT NOT NULL DEFAULT 0,
        chunks     INT NOT NULL DEFAULT 0,
        status     TEXT DEFAULT 'ready',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    # 长期记忆
    """CREATE TABLE IF NOT EXISTS long_term_memory (
        id            SERIAL PRIMARY KEY,
        content       TEXT NOT NULL,
        importance    FLOAT NOT NULL DEFAULT 0.5,
        embedding     JSONB,
        created_at    DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
        last_accessed DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW()),
        category      VARCHAR(64) NOT NULL DEFAULT '',
        tags          JSONB NOT NULL DEFAULT '[]'::jsonb,
        slot_hint     VARCHAR(64) NOT NULL DEFAULT '',
        score         DOUBLE PRECISION NOT NULL DEFAULT 0.0
    )""",
    # Migration: Schema-driven 装配列
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS created_at    DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())",
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS last_accessed DOUBLE PRECISION DEFAULT EXTRACT(EPOCH FROM NOW())",
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS category      VARCHAR(64) NOT NULL DEFAULT ''",
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS tags          JSONB NOT NULL DEFAULT '[]'::jsonb",
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS slot_hint     VARCHAR(64) NOT NULL DEFAULT ''",
    "ALTER TABLE long_term_memory ADD COLUMN IF NOT EXISTS score         DOUBLE PRECISION NOT NULL DEFAULT 0.0",
    "CREATE INDEX IF NOT EXISTS idx_ltm_category ON long_term_memory(category)",
    "CREATE INDEX IF NOT EXISTS idx_ltm_tags     ON long_term_memory USING GIN(tags)",
]


class PostgresClient:
    """PostgreSQL 平台客户端：连接池、ping、bootstrap、表级 CRUD。

    适用于 RAG 向量存储 + 长期记忆持久化。失败时优雅降级（status="disconnected"），
    不阻塞应用启动。
    """

    def __init__(self, cfg: Any):
        self.cfg = cfg
        self._conn = None
        self._pool = None
        self.status: str = "disconnected"
        self._connect()
        if self._conn is not None:
            self.bootstrap_schema()
        elif self._pool is not None:
            self.bootstrap_schema()

    # ─── 连接 ───

    def _connect(self) -> None:
        if not _HAS_PG:
            logger.warning("⚠️  psycopg2 未安装，PostgreSQL 不可用")
            return
        host = getattr(self.cfg, "pg_host", None)
        if not host:
            logger.warning("⚠️  PostgreSQL 未配置 (pg_host 为空)")
            return
        try:
            dsn = self._build_dsn()
            self._pool = pg_pool.ThreadedConnectionPool(2, 10, dsn=dsn)
            conn = self._pool.getconn()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            self._pool.putconn(conn)
            self.status = "connected"
            logger.info("✅ PostgreSQL 连接池已连接: %s", dsn)
        except Exception as e:
            logger.warning("⚠️  PostgreSQL 连接失败: %s", e)
            self._pool = None
            self.status = "disconnected"

    def _build_dsn(self) -> str:
        cfg = self.cfg
        host = getattr(cfg, "pg_host", "127.0.0.1") or "127.0.0.1"
        port = getattr(cfg, "pg_port", 5432) or 5432
        user = getattr(cfg, "pg_user", "postgres") or "postgres"
        password = getattr(cfg, "pg_password", "") or ""
        dbname = getattr(cfg, "pg_dbname", "agent_memory") or "agent_memory"
        return f"host={host} port={port} dbname={dbname} user={user} password={password}"

    # ─── 状态判断 ───

    def is_real(self) -> bool:
        return self._pool is not None

    def _borrow(self):
        if self._pool is not None:
            conn = self._pool.getconn()
            conn.autocommit = True
            return conn
        return None

    def _release(self, conn) -> None:
        if self._pool is not None and conn is not None:
            self._pool.putconn(conn)

    # ─── Schema bootstrap ───

    def bootstrap_schema(self) -> None:
        if not self.is_real():
            return
        conn = self._borrow()
        if conn is None:
            return
        try:
            with conn.cursor() as cur:
                for ddl in _DDLS:
                    try:
                        cur.execute(ddl)
                    except Exception as e:
                        logger.warning("⚠️  PG DDL 执行失败: %s\n  SQL: %s", e, ddl[:80])
            logger.info("✅ PostgreSQL 表结构已初始化")
        except Exception as e:
            logger.warning("⚠️  PG bootstrap 失败: %s", e)
        finally:
            self._release(conn)

    # ─── 通用 query / exec ───

    def query(self, sql: str, params: Optional[Sequence[Any]] = None) -> List[Tuple[Any, ...]]:
        if not self.is_real():
            return []
        conn = self._borrow()
        if conn is None:
            return []
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                return list(cur.fetchall())
        except Exception as e:
            logger.warning("⚠️  PG query 失败: %s", e)
            return []
        finally:
            self._release(conn)

    def exec(self, sql: str, params: Optional[Sequence[Any]] = None) -> int:
        if not self.is_real():
            return -1
        conn = self._borrow()
        if conn is None:
            return -1
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params or ())
                return cur.rowcount
        except Exception as e:
            logger.warning("⚠️  PG exec 失败: %s", e)
            return -1
        finally:
            self._release(conn)

    # ─── RAG CRUD ───

    def rag_insert_chunks(self, rows: List[Tuple]) -> int:
        """批量插入 chunks：(doc_hash, chunk_idx, content, embedding_json)。"""
        if not self.is_real() or not rows:
            return 0
        conn = self._borrow()
        if conn is None:
            return 0
        try:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO rag_chunks (doc_hash, chunk_idx, content, embedding) "
                    "VALUES (%s, %s, %s, %s::jsonb) "
                    "ON CONFLICT (doc_hash, chunk_idx) DO NOTHING",
                    [(r[0], r[1], r[2], r[3]) for r in rows],
                )
                return cur.rowcount
        except Exception as e:
            logger.warning("⚠️  PG rag_insert_chunks 失败: %s", e)
            return 0
        finally:
            self._release(conn)

    def rag_insert_doc(self, doc_hash: str, doc_name: str, size: int, chunks: int) -> bool:
        sql = ("INSERT INTO rag_docs (doc_hash, doc_name, size, chunks) "
               "VALUES (%s, %s, %s, %s) "
               "ON CONFLICT (doc_hash) DO UPDATE SET size=EXCLUDED.size, chunks=EXCLUDED.chunks")
        return self.exec(sql, (doc_hash, doc_name, size, chunks)) >= 0

    def rag_get_all_chunks(self) -> List[Dict[str, Any]]:
        rows = self.query("SELECT id, doc_hash, chunk_idx, content, embedding FROM rag_chunks ORDER BY id")
        result = []
        for r in rows:
            emb = r[4]
            if emb is not None and not isinstance(emb, (dict, list)):
                try:
                    emb = json.loads(emb)
                except Exception:
                    emb = None
            result.append({
                "id": r[0],
                "doc_hash": r[1],
                "chunk_idx": r[2],
                "content": r[3],
                "embedding": emb,
            })
        return result

    def rag_delete_doc(self, doc_hash: str) -> Dict[str, int]:
        """删除文档及分块，返回实际删除行数；SQL 失败时抛出异常。"""
        if not self.is_real():
            raise RuntimeError("PostgreSQL 未连接")

        deleted_chunks = self.exec(
            "DELETE FROM rag_chunks WHERE doc_hash=%s", (doc_hash,),
        )
        if deleted_chunks < 0:
            raise RuntimeError("PostgreSQL rag_chunks 删除失败")

        deleted_docs = self.exec(
            "DELETE FROM rag_docs WHERE doc_hash=%s", (doc_hash,),
        )
        if deleted_docs < 0:
            raise RuntimeError("PostgreSQL rag_docs 删除失败")

        logger.info(
            "PostgreSQL RAG 文档已删除: doc=%s chunks=%d docs=%d",
            doc_hash, deleted_chunks, deleted_docs,
        )
        return {"chunks": deleted_chunks, "documents": deleted_docs}

    def rag_chunk_count(self) -> int:
        rows = self.query("SELECT COUNT(*) FROM rag_chunks")
        return rows[0][0] if rows else 0

    # ─── 关闭 ───

    def close(self) -> None:
        if self._pool is not None:
            try:
                self._pool.closeall()
            except Exception as e:
                logger.warning("⚠️  PG 连接池关闭失败: %s", e)
            finally:
                self._pool = None
                self.status = "disconnected"


# ═══════════════════ 模块级单例 ═══════════════════

_pg_client: Optional[PostgresClient] = None


def get_pg_client(cfg: Any) -> PostgresClient:
    """获取 PostgreSQL 客户端全局单例。"""
    global _pg_client
    if _pg_client is None:
        _pg_client = PostgresClient(cfg)
    return _pg_client
