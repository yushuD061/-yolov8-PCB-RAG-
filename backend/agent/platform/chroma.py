"""
chroma — Chroma 向量数据库平台客户端：持久化、集合管理、RAG CRUD。
失败时降级到 mock（self._client 为 None），不阻塞应用启动。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _HAS_CHROMA = True
except ImportError:
    chromadb = None  # type: ignore
    _HAS_CHROMA = False


class ChromaClient:
    """Chroma 向量数据库客户端：持久化、集合管理、RAG CRUD。

    数据持久化到本地目录（PersistentClient），便于分发与备份。
    失败时优雅降级（is_real() 返回 False），不阻塞应用启动。
    """

    def __init__(self, cfg: Any):
        self.cfg = cfg
        self._client: Optional["chromadb.PersistentClient"] = None
        self._collection: Optional[Any] = None
        self.status: str = "disconnected"
        self._connect()

    # ─── 连接 ───

    def _connect(self) -> None:
        if not _HAS_CHROMA:
            logger.warning("⚠️  chromadb 未安装，Chroma 不可用")
            return
        path = getattr(self.cfg, "chroma_path", None)
        if not path:
            logger.warning("⚠️  Chroma 未配置 (chroma_path 为空)")
            return
        try:
            os.makedirs(path, exist_ok=True)
            settings = ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=False,
            )
            self._client = chromadb.PersistentClient(path=path, settings=settings)
            collection_name = getattr(self.cfg, "chroma_collection", "rag_chunks")
            self._collection = self._client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            self.status = "connected"
            logger.info("✅ Chroma 已连接: path=%s collection=%s", path, collection_name)
        except Exception as e:
            logger.warning("⚠️  Chroma 连接失败: %s", e)
            self._client = None
            self._collection = None
            self.status = "disconnected"

    # ─── 状态判断 ───

    def is_real(self) -> bool:
        return self._client is not None and self._collection is not None

    # ─── RAG CRUD ───

    def rag_insert_chunks(self, rows: List[Dict[str, Any]]) -> int:
        """批量 upsert chunks 到 Chroma collection。

        rows 每项格式：{"id": str, "content": str, "embedding": list[float],
                         "metadata": dict}  (metadata 中包含 doc_hash, chunk_idx 等)
        """
        if not self.is_real() or not rows:
            return 0
        try:
            ids = [r["id"] for r in rows]
            contents = [r["content"] for r in rows]
            embeddings = [r["embedding"] for r in rows]
            metadatas = [r.get("metadata", {}) for r in rows]

            self._collection.upsert(
                ids=ids,
                documents=contents,
                embeddings=embeddings,
                metadatas=metadatas,
            )
            logger.info("Chroma upsert: %d chunks", len(rows))
            return len(rows)
        except Exception as e:
            logger.warning("⚠️  Chroma rag_insert_chunks 失败: %s", e)
            return 0

    def rag_search(self, query_emb: List[float], top_k: int,
                   threshold: float = 0.0) -> List[Dict[str, Any]]:
        """向量相似度检索，返回带相似度的结果列表。"""
        if not self.is_real():
            return []
        try:
            result = self._collection.query(
                query_embeddings=[query_emb],
                n_results=top_k,
                include=["documents", "metadatas", "distances"],
            )
            if not result or not result.get("ids"):
                return []

            out: List[Dict[str, Any]] = []
            ids = result["ids"][0]
            distances = result["distances"][0]
            documents = result["documents"][0]
            metadatas = result["metadatas"][0]

            for i in range(len(ids)):
                # Chroma 返回的是 L2 distance，转为 cosine similarity
                # cosine distance = 1 - cosine_similarity
                # cosine_similarity = 1 - cosine_distance
                sim = max(0.0, 1.0 - distances[i])
                if sim < threshold:
                    continue
                meta = metadatas[i] if metadatas else {}
                out.append({
                    "id": ids[i],
                    "content": documents[i] if documents else "",
                    "embedding": [],
                    "metadata": meta,
                    "score": sim,
                })
            return out
        except Exception as e:
            logger.warning("⚠️  Chroma rag_search 失败: %s", e)
            return []

    def rag_get_all_chunks(self) -> List[Dict[str, Any]]:
        """获取 collection 中所有记录（不含 embedding 以节省带宽）。"""
        if not self.is_real():
            return []
        try:
            result = self._collection.get(
                include=["documents", "metadatas"],
            )
            if not result or not result.get("ids"):
                return []
            out: List[Dict[str, Any]] = []
            for i in range(len(result["ids"])):
                meta = result["metadatas"][i] if result.get("metadatas") else {}
                out.append({
                    "id": result["ids"][i],
                    "content": result["documents"][i] if result.get("documents") else "",
                    "metadata": meta,
                })
            return out
        except Exception as e:
            logger.warning("⚠️  Chroma rag_get_all_chunks 失败: %s", e)
            return []

    def rag_delete_doc(self, doc_hash: str) -> bool:
        """按 doc_hash metadata 过滤删除文档的所有 chunks。"""
        if not self.is_real():
            return False
        try:
            self._collection.delete(where={"doc_hash": doc_hash})
            return True
        except Exception as e:
            logger.warning("⚠️  Chroma rag_delete_doc 失败: %s", e)
            return False

    def rag_chunk_count(self) -> int:
        """collection 中的总记录数。"""
        if not self.is_real():
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.warning("⚠️  Chroma count 失败: %s", e)
            return 0

    # ─── 关闭 ───

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client = None
                self._collection = None
                self.status = "disconnected"
                logger.info("Chroma 已关闭")
            except Exception as e:
                logger.warning("⚠️  Chroma 关闭失败: %s", e)


# ═══════════════════ 模块级单例 ═══════════════════

_chroma_client: Optional[ChromaClient] = None


def get_chroma_client(cfg: Any) -> ChromaClient:
    """获取 Chroma 客户端全局单例。"""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = ChromaClient(cfg)
    return _chroma_client
