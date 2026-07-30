"""
RAG 核心 — 数据模型 / SQLite 存储 / TF-IDF 向量化检索 / LLM 合成。

依赖：
- splitter.py 提供 RecursiveSplitter
- sklearn TfidfVectorizer + 余弦相似度（稀疏向量检索）
- jieba 中文分词（可选的 tokenizer）
"""

import hashlib
import json
import logging
import math
import os
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from agent.rag.splitter import RecursiveSplitter
from agent.rag.reranker import LLMReranker
from agent.rag.rewriter import LLMRewriter, HistoryMessage
from agent.platform.postgres import PostgresClient
from agent.platform.chroma import ChromaClient

logger = logging.getLogger("rag_core")


def _sqlite_utc_to_iso(value: str) -> str:
    """将 SQLite datetime('now') 的无时区 UTC 文本转换为 ISO 8601。"""
    value = (value or "").strip()
    if not value:
        return ""
    if value.endswith("Z") or "+" in value[10:]:
        return value
    return f"{value.replace(' ', 'T')}Z"

# ═══════════════════ 数据模型 ═══════════════════

@dataclass
class RagChunk:
    """存储在 SQLite 中的单个文本块。"""
    id: int = 0
    doc_id: str = ""
    doc_name: str = ""
    chunk_index: int = 0
    content: str = ""
    parent_content: str = ""  # 父块内容（实现父子块检索）


@dataclass
class RetrievalHit:
    """一次检索命中的结果。"""
    chunk: RagChunk
    score: float
    source: str = "tfidf"


# ═══════════════════ SQLite 持久化 ═══════════════════

class RagStore:
    """SQLite 分块存储 — 管理 rag_chunks / rag_docs 两张表。"""

    def __init__(self, db_path: str = "data/rag.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._lock = threading.Lock()
        self._init_table()

    def _init_table(self):
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_chunks (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    doc_id    TEXT NOT NULL,
                    doc_name  TEXT NOT NULL,
                    chunk_idx INTEGER NOT NULL,
                    content   TEXT NOT NULL,
                    parent    TEXT DEFAULT ''
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS rag_docs (
                    doc_id   TEXT PRIMARY KEY,
                    doc_name TEXT NOT NULL,
                    size     INTEGER DEFAULT 0,
                    chunks   INTEGER DEFAULT 0,
                    status   TEXT DEFAULT 'ready',
                    created_at TEXT DEFAULT (datetime('now'))
                )
            """)
            self._conn.commit()

    def add_chunks(self, doc_id: str, doc_name: str,
                   chunks: List[str], parents: List[str]) -> int:
        """批量插入块并更新文档元数据。"""
        with self._lock:
            cur = self._conn.cursor()
            for i, (chunk, parent) in enumerate(zip(chunks, parents)):
                cur.execute(
                    "INSERT INTO rag_chunks (doc_id, doc_name, chunk_idx, content, parent) "
                    "VALUES (?,?,?,?,?)",
                    (doc_id, doc_name, i, chunk, parent),
                )
            cur.execute(
                "INSERT OR REPLACE INTO rag_docs (doc_id, doc_name, size, chunks, status) "
                "VALUES (?,?,?,?,'ready')",
                (doc_id, doc_name, sum(len(c) for c in chunks), len(chunks)),
            )
            self._conn.commit()
            return len(chunks)

    def get_all_chunks(self) -> List[RagChunk]:
        """返回所有块，按 id 升序。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, doc_id, doc_name, chunk_idx, content, parent "
                "FROM rag_chunks ORDER BY id"
            ).fetchall()
        return [
            RagChunk(id=r[0], doc_id=r[1], doc_name=r[2],
                     chunk_index=r[3], content=r[4], parent_content=r[5])
            for r in rows
        ]

    def get_docs(self) -> List[dict]:
        """返回所有文档摘要列表（用于前端展示）。"""
        with self._lock:
            rows = self._conn.execute(
                "SELECT doc_id, doc_name, size, chunks, status, created_at "
                "FROM rag_docs ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "size": r[2],
             "chunks": r[3], "status": r[4],
             "uploadedAt": _sqlite_utc_to_iso(r[5])}
            for r in rows
        ]

    def delete_doc(self, doc_id: str):
        """删除文档及其所有块。"""
        with self._lock:
            self._conn.execute("DELETE FROM rag_chunks WHERE doc_id=?", (doc_id,))
            self._conn.execute("DELETE FROM rag_docs WHERE doc_id=?", (doc_id,))
            self._conn.commit()

    def chunk_count(self) -> int:
        """当前总块数。"""
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM rag_chunks").fetchone()[0]

    def close(self) -> None:
        """显式释放 SQLite 连接，供评估/测试的临时索引可靠清理。"""
        with self._lock:
            self._conn.close()


# ═══════════════════ RAG 引擎 ═══════════════════

class RagEngine:
    """RAG 引擎：文档切分 → TF-IDF 向量化 → 入库 → 检索 → LLM 合成。"""

    def __init__(self, db_path: str = "data/rag.db",
                 chunk_size: int = 500, chunk_overlap: int = 50,
                 top_k: int = 3):
        self.store = RagStore(db_path)
        self.splitter = RecursiveSplitter(chunk_size, chunk_overlap)
        self.top_k = top_k

        # TF-IDF 惰性构建
        self._vectorizer: Optional[TfidfVectorizer] = None
        self._char_vectorizer: Optional[TfidfVectorizer] = None
        self._chunk_texts: List[str] = []
        self._tfidf_matrix = None
        self._char_tfidf_matrix = None
        self._dirty = True
        # LangSmith 等并发调用会同时触发首次检索；矩阵必须只初始化一次并原子发布。
        self._tfidf_lock = threading.RLock()
        from agent.config import get_agent_config
        _cfg = get_agent_config()
        self._hybrid_enabled = _cfg.rag_hybrid_enabled
        self._char_weight = max(0.0, min(1.0, _cfg.rag_char_weight))

        # LLM 生成函数（由外部注入）
        self._generate_fn: Optional[Callable[[str, str], str]] = None

        # LLM Reranker（可选，由外部注入）
        self._reranker: Optional[LLMReranker] = None

        # LLM Query Rewriter（可选，由外部注入）
        self._rewriter: Optional[LLMRewriter] = None

        # PG 向量存储（可选）
        self._pg: Optional[PostgresClient] = None
        # Chroma 向量存储（可选）
        self._chroma: Optional[ChromaClient] = None
        self._embed_fn: Optional[Callable[[str], Optional[List[float]]]] = None
        self._vector_enabled = False
        self._init_vector_backend()

    def set_generate_fn(self, fn: Callable[[str, str], str]):
        """注入 LLM 答案生成函数: fn(system_prompt, user_message) -> str"""
        self._generate_fn = fn

    def set_reranker(self, generate_fn: Callable[[str, str], str]):
        """注入 LLM 精排器。复用同一个 LLM 调用函数。"""
        self._reranker = LLMReranker(generate_fn)

    def set_rewriter(self, generate_fn: Callable[[str, str], str]):
        """注入 LLM 查询改写器。复用同一个 LLM 调用函数。

        改写数量由 AgentConfig.rag_rewrite_queries 控制（0 或 1 表示禁用）。
        """
        from agent.config import get_agent_config
        num = get_agent_config().rag_rewrite_queries
        if num > 1:
            self._rewriter = LLMRewriter(generate_fn, num_queries=num)
            logger.info(f"Query Rewriter 已启用 (num_queries={num})")
        else:
            self._rewriter = None
            logger.info("Query Rewriter 已禁用 (rag_rewrite_queries=%d)", num)

    def _init_vector_backend(self):
        """初始化向量后端（Chroma 优先，PG 次之）；失败则回退到 TF-IDF 模式。"""
        from agent.config import get_agent_config
        cfg = get_agent_config()
        if not cfg.rag_vector_enabled:
            logger.info("RAG 向量检索未启用 (RAG_VECTOR_ENABLED=false)，使用 TF-IDF")
            return

        # Chroma 优先
        if cfg.chroma_enabled:
            self._chroma = ChromaClient(cfg)
            if self._chroma.is_real():
                from services.llm_service import call_embedding_api
                self._embed_fn = lambda text: call_embedding_api(text)
                self._vector_enabled = True
                logger.info("RAG 向量检索已启用 (Chroma + embedding)")
                return
            else:
                logger.warning("Chroma 不可用，尝试 PG")
                self._chroma = None

        # PG 次之
        self._pg = PostgresClient(cfg)
        if self._pg.is_real():
            from services.llm_service import call_embedding_api
            self._embed_fn = lambda text: call_embedding_api(text)
            self._vector_enabled = True
            logger.info("RAG 向量检索已启用 (PG + embedding)")
            return
        else:
            self._pg = None

        logger.warning("所有向量后端均不可用，回退到 SQLite + TF-IDF")

    @property
    def loaded(self) -> bool:
        """知识库是否有数据。"""
        return self.store.chunk_count() > 0

    def close(self) -> None:
        """释放引擎持有的本地存储资源。"""
        self.store.close()

    # ── 入库 ──

    def ingest(self, text: str, doc_name: str = "document") -> int:
        """切分文档并入库，返回 chunk 数量。

        采用父子块策略：
        - 父块 = splitter 切出的主要段落（chunk_size）
        - 子块 = 对每个父块再对半切分（chunk_size // 2）
        - 检索命中子块时，提供父块作为 context
        """
        doc_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        doc_id = f"{doc_hash}"

        # 父块切分
        parent_chunks = self.splitter.split_text(text)

        # 子块切分（比父块更细）
        child_splitter = RecursiveSplitter(
            self.splitter.chunk_size // 2,
            self.splitter.chunk_overlap // 2,
        )
        all_children: List[str] = []
        all_parents: List[str] = []
        for parent in parent_chunks:
            children = child_splitter.split_text(parent)
            for child in children:
                all_children.append(child)
                all_parents.append(parent)

        if not all_children:
            return 0

        count = self.store.add_chunks(doc_id, doc_name, all_children, all_parents)
        self._dirty = True

        # 向量后端同步（Chroma 或 PG）
        if self._vector_enabled and self._embed_fn is not None:
            try:
                emb_data = []
                for child in all_children:
                    emb = self._embed_fn(child)
                    emb_data.append(emb if emb else [])

                if self._chroma is not None:
                    chroma_rows = [
                        {
                            "id": f"{doc_hash}_{i}",
                            "content": all_children[i],
                            "embedding": emb_data[i],
                            "metadata": {
                                "doc_hash": doc_hash,
                                "doc_name": doc_name,
                                "chunk_idx": i,
                            },
                        }
                        for i in range(len(all_children))
                        if emb_data[i]
                    ]
                    if chroma_rows:
                        self._chroma.rag_insert_chunks(chroma_rows)
                        logger.info("Chroma 向量同步完成: doc=%s chunks=%d", doc_name, len(chroma_rows))

                if self._pg is not None:
                    emb_jsons = [json.dumps(e) if e else "null" for e in emb_data]
                    pg_rows = [
                        (doc_hash, i, all_children[i], emb_jsons[i])
                        for i in range(len(all_children))
                    ]
                    self._pg.rag_insert_chunks(pg_rows)
                    self._pg.rag_insert_doc(
                        doc_hash, doc_name,
                        sum(len(c) for c in all_children), len(all_children),
                    )
                    logger.info("PG 向量同步完成: doc=%s chunks=%d", doc_name, len(all_children))
            except Exception as e:
                logger.warning("向量同步失败: %s", e)

        logger.info(f"RAG 入库完成: doc={doc_name} chunks={count}")
        return count

    # ── 检索 + 合成 ──

    def query(self, question: str, extra_context: str = "",
              history: List[HistoryMessage] = []) -> Tuple[str, List[dict]]:
        """检索并生成 LLM 回答。

        参数：
            question:      用户问题
            extra_context: 额外追加到 LLM 上下文的系统数据（如检测统计）
            history:       对话历史（用于查询改写消歧）
        返回：
            (answer_text, sources_list)
        """
        if not self.loaded:
            if extra_context:
                return self._compose(question, extra_context, []), []
            return "知识库为空，且暂无可分析的检测历史。", []

        # 向量召回作为候选通道；随后与本地混合 TF-IDF 结果做 RRF 融合。
        vector_hits: List[RetrievalHit] = []
        if self._vector_enabled and self._embed_fn is not None:
            q_emb = self._embed_fn(question)
            if q_emb:
                if self._chroma is not None:
                    vector_hits = self._chroma_vector_search(q_emb, self.top_k * 4)
                if not vector_hits and self._pg is not None:
                    vector_hits = self._pg_vector_search(q_emb, self.top_k * 4)

        # 参考企业级 hybrid 检索：先扩大候选池，再交给 listwise reranker 精排。
        # 候选池过小会让词面不相似但语义直接相关的段落永远没有机会进入精排。
        candidate_k = max(self.top_k * (8 if self._reranker else 2), 10)

        # 当 rewriter 可用时，改写为多个子查询做多路检索
        if self._rewriter:
            sub_queries = self._rewriter.rewrite(question, history)
            if len(sub_queries) > 1:
                logger.info("多路检索: 改写为 %d 个子查询", len(sub_queries))
                hits = self._multi_query_search(sub_queries, candidate_k)
            else:
                hits = self._search(question, candidate_k)
        else:
            hits = self._search(question, candidate_k)

        if vector_hits:
            from agent.rag.hybrid import rrf_fuse
            lexical_count = len(hits)
            hits = rrf_fuse(
                [self._deduplicate_hits(vector_hits), self._deduplicate_hits(hits)],
                top_k=candidate_k,
            )
            logger.info(
                "混合召回(RRF): vector=%d lexical=%d fused=%d",
                len(vector_hits), lexical_count, len(hits),
            )

        if not hits and not extra_context:
            return "知识库中未找到相关内容。", []

        # LLM Reranker 精排（如果有）
        hits = self._deduplicate_hits(hits)
        if self._reranker and len(hits) > 1:
            hits = self._reranker.rerank(question, hits, self.top_k)
        else:
            hits = hits[:self.top_k]

        sources = [
            {
                "doc_name": h.chunk.doc_name,
                "content": h.chunk.parent_content or h.chunk.content[:200],
                "score": round(h.score, 4),
                "source": h.source,
            }
            for h in hits
        ]

        context = "\n\n".join(h.chunk.parent_content or h.chunk.content for h in hits)
        if extra_context:
            context += "\n\n" + extra_context

        answer = self._compose(question, context, sources)
        return answer, sources

    # ── 向量检索 ──

    @staticmethod
    def _deduplicate_hits(hits: List[RetrievalHit]) -> List[RetrievalHit]:
        """按文档和父块去重，避免同一父块重复占用上下文窗口。"""
        unique: List[RetrievalHit] = []
        seen = set()
        for hit in hits:
            context = hit.chunk.parent_content or hit.chunk.content
            key = (hit.chunk.doc_id, context.strip())
            if key in seen:
                continue
            seen.add(key)
            unique.append(hit)
        return unique

    def _multi_query_search(self, sub_queries: List[str], top_k: int) -> List[RetrievalHit]:
        """多路检索 + RRF 融合（优于原始 cosine score 直接合并）。"""
        from agent.rag.hybrid import multi_query_search as _mq
        fused = _mq(self._search, sub_queries, top_k)
        if fused:
            logger.info("多路检索(RRF): %d 个子查询 → %d 个结果",
                         len(sub_queries), len(fused))
        return fused

    def _search(self, question: str, top_k: int) -> List[RetrievalHit]:
        """词级/字符级 TF-IDF 混合检索，兼顾术语、缩写和改写后的英文查询。"""
        self._ensure_tfidf()

        chunks = self._chunks_cache
        if not chunks or self._tfidf_matrix is None:
            return []

        with self._tfidf_lock:
            word_vec = self._vectorizer.transform([question])
            word_sims = cosine_similarity(word_vec, self._tfidf_matrix)[0]
            sims = word_sims
            source = "tfidf-word"
            if (
                self._hybrid_enabled
                and self._char_vectorizer is not None
                and self._char_tfidf_matrix is not None
            ):
                char_vec = self._char_vectorizer.transform([question])
                char_sims = cosine_similarity(char_vec, self._char_tfidf_matrix)[0]
                sims = (1.0 - self._char_weight) * word_sims + self._char_weight * char_sims
                source = "tfidf-word+char"

        top_indices = np.argsort(sims)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if sims[idx] < 0.001:
                continue
            results.append(
                RetrievalHit(chunk=chunks[idx], score=float(sims[idx]), source=source)
            )
        return results

    def _pg_vector_search(self, query_emb: List[float], top_k: int) -> List[RetrievalHit]:
        """PG 向量相似度检索 — 余弦相似度。"""
        from agent.config import get_agent_config
        threshold = get_agent_config().rag_vector_threshold

        pg_chunks = self._pg.rag_get_all_chunks()
        if not pg_chunks:
            return []

        scored = []
        for row in pg_chunks:
            emb = row.get("embedding")
            if emb is None:
                continue
            if isinstance(emb, str):
                try:
                    emb = json.loads(emb)
                except Exception:
                    continue
            if not emb or len(emb) != len(query_emb):
                continue
            sim = self._cosine_similarity(query_emb, emb)
            if sim < threshold:
                continue
            scored.append((row, sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        results = []
        for row, sim in scored[:top_k]:
            chunk = RagChunk(
                id=row["id"], doc_id=row["doc_hash"], doc_name="",
                chunk_index=row["chunk_idx"], content=row["content"],
                parent_content=row["content"],
            )
            results.append(RetrievalHit(chunk=chunk, score=float(sim), source="pg+embedding"))
        return results

    def _chroma_vector_search(self, query_emb: List[float], top_k: int) -> List[RetrievalHit]:
        """Chroma 向量相似度检索。"""
        from agent.config import get_agent_config
        threshold = get_agent_config().rag_vector_threshold

        chroma_results = self._chroma.rag_search(query_emb, top_k, threshold)
        if not chroma_results:
            return []

        results = []
        for row in chroma_results:
            meta = row.get("metadata", {}) or {}
            chunk = RagChunk(
                id=0,
                doc_id=meta.get("doc_hash", ""),
                doc_name=meta.get("doc_name", ""),
                chunk_index=meta.get("chunk_idx", 0),
                content=row.get("content", ""),
                parent_content=row.get("content", ""),
            )
            results.append(RetrievalHit(
                chunk=chunk,
                score=float(row.get("score", 0)),
                source="chroma+embedding",
            ))
        return results

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def delete_doc(self, doc_id: str) -> dict:
        """删除文档；先删除外部向量存储，成功后再删除 SQLite。"""
        result = {
            "documentId": doc_id,
            "postgres": None,
            "chroma": None,
            "sqlite": False,
        }

        # 外部存储失败时保留 SQLite 文档，使前端仍可见并允许重试。
        if self._chroma is not None:
            if not self._chroma.rag_delete_doc(doc_id):
                raise RuntimeError("Chroma 文档删除失败")
            result["chroma"] = True

        if self._pg is not None:
            result["postgres"] = self._pg.rag_delete_doc(doc_id)

        self.store.delete_doc(doc_id)
        self._dirty = True
        result["sqlite"] = True
        return result

    # ── TF-IDF 矩阵构建 ──

    _chunks_cache: List[RagChunk] = []

    def _ensure_tfidf(self):
        """惰性构建/重建 TF-IDF 矩阵。"""
        if not self._dirty and self._tfidf_matrix is not None:
            return

        with self._tfidf_lock:
            # 获取锁前另一个线程可能已经完成初始化，因此必须再次检查。
            if not self._dirty and self._tfidf_matrix is not None:
                return

            chunks = self.store.get_all_chunks()
            texts = [c.content for c in chunks]

            if not texts:
                self._chunks_cache = []
                self._tfidf_matrix = None
                self._char_tfidf_matrix = None
                self._vectorizer = None
                self._char_vectorizer = None
                self._dirty = False
                return

            # jieba 中文分词 tokenizer（缓存到项目 data 目录）
            def _tokenize(text: str):
                import os
                os.environ.setdefault(
                    "JIEBA_CACHE_FILE",
                    os.path.join(os.path.dirname(__file__), "..", "..", "data", "jieba.cache"),
                )
                import jieba
                return list(jieba.cut(text))

            # 先在局部变量中完整拟合，再一次性发布，避免其他线程看到半初始化对象。
            vectorizer = TfidfVectorizer(
                max_features=5000,
                tokenizer=_tokenize,
                token_pattern=None,  # 禁用默认正则，完全由 jieba 控制
            )
            matrix = vectorizer.fit_transform(texts)
            feature_count = len(vectorizer.get_feature_names_out())
            char_vectorizer = None
            char_matrix = None
            char_feature_count = 0
            if self._hybrid_enabled:
                char_vectorizer = TfidfVectorizer(
                    analyzer="char_wb",
                    ngram_range=(2, 5),
                    min_df=1,
                    max_features=12000,
                    sublinear_tf=True,
                )
                char_matrix = char_vectorizer.fit_transform(texts)
                char_feature_count = len(char_vectorizer.get_feature_names_out())

            self._chunks_cache = chunks
            self._vectorizer = vectorizer
            self._tfidf_matrix = matrix
            self._char_vectorizer = char_vectorizer
            self._char_tfidf_matrix = char_matrix
            self._chunk_texts = texts
            self._dirty = False
            logger.info(
                "混合 TF-IDF 矩阵构建完成: %d chunks, word=%d char=%d 特征",
                len(texts), feature_count, char_feature_count,
            )

    # ── LLM 合成 ──

    def _compose(self, question: str, context: str, sources: List[dict]) -> str:
        """用 LLM 合成最终回答；无 LLM 时降级返回检索摘要。"""
        if self._generate_fn:
            print(f"[RAG compose] 调用 LLM, context长度={len(context)}", flush=True)
            system_prompt = (
                "你是一个 PCB 缺陷检测技术专家。请仅根据提供的文档内容回答问题，"
                "不要编造信息。如果文档不足以回答，请说明。回答简洁专业。"
            )
            user_msg = f"参考文档：\n{context}\n\n问题：{question}"
            try:
                result = self._generate_fn(system_prompt, user_msg)
                if result and result.strip():
                    return result
                print(f"[RAG compose] LLM 返回空，降级", flush=True)
            except Exception as e:
                print(f"[RAG compose] LLM 异常: {e}", flush=True)
        else:
            print(f"[RAG compose] 无 LLM 生成函数，返回检索摘要", flush=True)

        # 降级：返回检索摘要
        if not sources and context:
            return (
                "**检测历史统计**\n\n"
                f"问题：{question}\n\n"
                f"{context}\n\n"
                "当前未启用大模型生成，以上为系统根据检测批次直接计算的统计数据。"
            )

        doc_list = "\n".join(
            f"- [{s['doc_name']}] (相关度 {s['score']:.2f}) {s['content'][:100]}..."
            for s in sources
        )
        return (
            f"**RAG 检索结果**\n\n"
            f"问题：{question}\n\n"
            f"找到 {len(sources)} 个相关文档段落：\n{doc_list}"
        )


# ═══════════════════ 全局单例 ═══════════════════

_rag_engine: Optional[RagEngine] = None


def get_rag_engine() -> RagEngine:
    """获取 RAG 引擎全局单例（线程安全，首次调用时惰性初始化）。"""
    global _rag_engine
    if _rag_engine is None:
        from agent.config import get_agent_config
        cfg = get_agent_config()
        db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "rag.db")
        _rag_engine = RagEngine(
            db_path=os.path.abspath(db_path),
            chunk_size=cfg.rag_chunk_size,
            chunk_overlap=cfg.rag_chunk_overlap,
            top_k=cfg.rag_top_k,
        )
    return _rag_engine
