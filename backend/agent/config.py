"""
agent 配置加载器 — 读取 agent/.env 文件（通过 python-dotenv）。
"""

import os
from dataclasses import dataclass
from typing import Dict
from dotenv import dotenv_values


@dataclass
class AgentConfig:
    """Agent 模块配置，优先读环境变量，回退到 .env 文件。"""
    # LLM
    llm_endpoint: str = "https://api.openai.com/v1/chat/completions"
    llm_api_key: str = ""
    llm_model: str = "gpt-3.5-turbo"
    # RAG
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 3
    rag_rewrite_queries: int = 3  # 0 或 1 表示禁用改写
    rag_reranker_enabled: bool = True  # 对召回候选做 listwise 精排，减少首条噪声对答案的影响
    rag_hybrid_enabled: bool = True  # 词级 + 字符级稀疏检索；有向量后端时再与向量结果做 RRF
    rag_char_weight: float = 0.35

    # Vector DB (PostgreSQL)
    pg_enabled: bool = False
    pg_host: str = "127.0.0.1"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = ""
    pg_dbname: str = "agent_memory"
    # Vector DB (Chroma)
    chroma_enabled: bool = False
    chroma_path: str = "data/chroma"
    chroma_collection: str = "rag_chunks"
    # Embedding
    embedding_enabled: bool = False
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_dim: int = 512
    embedding_endpoint: str = ""
    # RAG 向量检索
    rag_vector_enabled: bool = False
    rag_vector_top_k: int = 10
    rag_vector_threshold: float = 0.35


def load_agent_config(dotenv_path: str | None = None) -> AgentConfig:
    """加载 agent 配置。先读 .env，环境变量优先级更高。"""
    cfg = AgentConfig()

    # 1. 读 .env 文件
    if dotenv_path is None:
        dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    env_vars = dotenv_values(dotenv_path) if os.path.isfile(dotenv_path) else {}

    # 2. 环境变量覆盖（os.environ 优先级更高）
    env_vars.update({k: v for k, v in os.environ.items() if v})

    # 2.5 将 LLM / Embedding 相关配置注入 os.environ，供 call_embedding_api
    # 等直接读取 os.environ 的下游使用（dotenv_values 只读取、不写入 os.environ）。
    # setdefault 保留真实环境变量的优先级。
    for _k in ("LLM_ENDPOINT", "LLM_API_KEY", "LLM_MODEL",
               "EMBEDDING_ENDPOINT", "EMBEDDING_API_KEY", "EMBEDDING_MODEL", "EMBEDDING_DIM"):
        if _k in env_vars and env_vars[_k]:
            os.environ.setdefault(_k, env_vars[_k])

    # 3. 映射到 AgentConfig
    _str = env_vars.get
    _int = lambda k, d: int(env_vars[k]) if k in env_vars else d
    _bool = lambda k, d: env_vars[k].strip().lower() in ("1", "true", "yes") if k in env_vars else d
    _float = lambda k, d: float(env_vars[k]) if k in env_vars else d

    cfg.llm_endpoint = _str("LLM_ENDPOINT", cfg.llm_endpoint)
    cfg.llm_api_key = _str("LLM_API_KEY", cfg.llm_api_key)
    cfg.llm_model = _str("LLM_MODEL", cfg.llm_model)
    cfg.rag_chunk_size = _int("RAG_CHUNK_SIZE", cfg.rag_chunk_size)
    cfg.rag_chunk_overlap = _int("RAG_CHUNK_OVERLAP", cfg.rag_chunk_overlap)
    cfg.rag_top_k = _int("RAG_TOP_K", cfg.rag_top_k)
    cfg.rag_rewrite_queries = _int("RAG_REWRITE_QUERIES", cfg.rag_rewrite_queries)
    cfg.rag_reranker_enabled = _bool("RAG_RERANKER_ENABLED", cfg.rag_reranker_enabled)
    cfg.rag_hybrid_enabled = _bool("RAG_HYBRID_ENABLED", cfg.rag_hybrid_enabled)
    cfg.rag_char_weight = _float("RAG_CHAR_WEIGHT", cfg.rag_char_weight)

    cfg.pg_enabled = _bool("PG_ENABLED", cfg.pg_enabled)
    cfg.pg_host = _str("PG_HOST", cfg.pg_host)
    cfg.pg_port = _int("PG_PORT", cfg.pg_port)
    cfg.pg_user = _str("PG_USER", cfg.pg_user)
    cfg.pg_password = _str("PG_PASSWORD", cfg.pg_password)
    cfg.pg_dbname = _str("PG_DBNAME", cfg.pg_dbname)
    cfg.chroma_enabled = _bool("CHROMA_ENABLED", cfg.chroma_enabled)
    cfg.chroma_path = _str("CHROMA_PATH", cfg.chroma_path)
    cfg.chroma_collection = _str("CHROMA_COLLECTION", cfg.chroma_collection)
    cfg.embedding_enabled = _bool("EMBEDDING_ENABLED", cfg.embedding_enabled)
    cfg.embedding_model = _str("EMBEDDING_MODEL", cfg.embedding_model)
    cfg.embedding_dim = _int("EMBEDDING_DIM", cfg.embedding_dim)
    cfg.embedding_endpoint = _str("EMBEDDING_ENDPOINT", cfg.embedding_endpoint)
    cfg.rag_vector_enabled = _bool("RAG_VECTOR_ENABLED", cfg.rag_vector_enabled)
    cfg.rag_vector_top_k = _int("RAG_VECTOR_TOP_K", cfg.rag_vector_top_k)
    cfg.rag_vector_threshold = _float("RAG_VECTOR_THRESHOLD", cfg.rag_vector_threshold)

    return cfg


# 模块级单例
_agent_config: AgentConfig | None = None


def get_agent_config() -> AgentConfig:
    global _agent_config
    if _agent_config is None:
        _agent_config = load_agent_config()
    return _agent_config
