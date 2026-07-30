"""
WS / REST 跨模块数据契约 — 集中定义消息结构，替代裸 dict。

遵循 agent.rag.rag_engine 的范式：先定义数据类型，再设计逻辑。
"""

from dataclasses import dataclass, field
from typing import Any, Literal


# ═══════════════════ WS 请求/响应 ═══════════════════

@dataclass
class WSRequest:
    """前端 → 后端 WebSocket 请求帧。"""
    id: str
    method: str
    channel: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class WSPushMessage:
    """后端 → 前端 WebSocket 推送帧。"""
    type: str
    data: Any

    def to_dict(self) -> dict:
        return {"type": self.type, "data": self.data}


# ═══════════════════ LLM 配置 ═══════════════════

@dataclass
class LlmApiConfig:
    """OpenAI 兼容 LLM API 调用配置。"""
    endpoint: str
    api_key: str
    model: str = "gpt-3.5-turbo"


# ═══════════════════ RAG 来源 ═══════════════════

@dataclass
class RagQueryResult:
    """RAG 检索问答返回结构。"""
    answer: str
    sources: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"answer": self.answer, "sources": self.sources}