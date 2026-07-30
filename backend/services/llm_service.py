"""
LLM 服务 — OpenAI 兼容 API 调用 + AI 预设报告。
"""

import json
import logging
import os
import urllib.request
from urllib.parse import urlparse
from typing import List, Optional

from langsmith import traceable

logger = logging.getLogger(__name__)


# ═══════════════════ 数据结构 ═══════════════════
# 见 schemas.py: LlmApiConfig

# ═══════════════════ 预设报告 ═══════════════════

def get_ai_preset() -> str:
    """AI 预设报告 — PCB 缺陷分析"""
    return (
        "**【PCB 缺陷检测 AI 分析报告】**\n\n"
        "1. **缺陷数量**\n"
        "   * 检测到多处 PCB 缺陷，需关注漏孔和短路类缺陷。\n"
        "2. **严重性评估**\n"
        "   * 开路和短路类缺陷影响电气连接，建议优先处理。\n"
        "3. **建议**\n"
        "   * 检查生产工艺中的蚀刻和钻孔工序，排查设备异常。"
    )


# ═══════════════════ LLM 调用 ═══════════════════

def _trace_inputs(inputs: dict) -> dict:
    """LangSmith 输入脱敏：保留评估所需 prompt，绝不上传 API key。"""
    cfg = inputs.get("cfg") or {}
    return {
        "model": cfg.get("model", ""),
        "endpoint_host": urlparse(cfg.get("endpoint", "")).hostname or "",
        "system_prompt": inputs.get("system_prompt", ""),
        "user_message": inputs.get("user_message", ""),
        "max_tokens": inputs.get("max_tokens", 1024),
        "temperature": inputs.get("temperature", 0.3),
    }


def _invocation_params(inputs: dict) -> dict:
    cfg = inputs.get("cfg") or {}
    host = urlparse(cfg.get("endpoint", "")).hostname or ""
    provider = "deepseek" if "deepseek" in host.lower() else "openai_compatible"
    return {
        "ls_provider": provider,
        "ls_model_name": cfg.get("model", ""),
        "ls_temperature": inputs.get("temperature", 0.3),
        "ls_max_tokens": inputs.get("max_tokens", 1024),
    }


def _optional_float(cfg: dict, key: str, env_key: str) -> Optional[float]:
    value = cfg.get(key)
    if value in (None, "") and env_key:
        value = os.getenv(env_key, "")
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _usage_metadata(result: dict, cfg: dict) -> Optional[dict]:
    """把 OpenAI 兼容 usage 转为 LangSmith token/cost 标准字段。"""
    usage = result.get("usage") or {}
    input_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    output_tokens = int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    )
    total_tokens = int(usage.get("total_tokens") or input_tokens + output_tokens)
    if not (input_tokens or output_tokens or total_tokens):
        return None

    metadata: dict = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
    cached_tokens = int(
        (usage.get("prompt_tokens_details") or {}).get("cached_tokens")
        or usage.get("prompt_cache_hit_tokens")
        or 0
    )
    if cached_tokens:
        metadata["input_token_details"] = {"cache_read": cached_tokens}

    input_rate = _optional_float(cfg, "inputCostPerMillion", "LLM_INPUT_COST_PER_MILLION")
    cached_rate = _optional_float(
        cfg, "cachedInputCostPerMillion", "LLM_CACHED_INPUT_COST_PER_MILLION"
    )
    output_rate = _optional_float(
        cfg, "outputCostPerMillion", "LLM_OUTPUT_COST_PER_MILLION"
    )
    input_cost = _optional_float(usage, "input_cost", "")
    if input_rate is not None:
        normal_tokens = max(0, input_tokens - cached_tokens)
        effective_cached_rate = cached_rate if cached_rate is not None else input_rate
        input_cost = (
            normal_tokens * input_rate + cached_tokens * effective_cached_rate
        ) / 1_000_000
    if input_cost is not None:
        metadata["input_cost"] = input_cost
    output_cost = _optional_float(usage, "output_cost", "")
    if output_rate is not None:
        output_cost = output_tokens * output_rate / 1_000_000
    if output_cost is not None:
        metadata["output_cost"] = output_cost
    provider_total_cost = _optional_float(usage, "total_cost", "")
    if provider_total_cost is not None:
        metadata["total_cost"] = provider_total_cost
    elif input_cost is not None or output_cost is not None:
        metadata["total_cost"] = (input_cost or 0.0) + (output_cost or 0.0)
    return metadata


@traceable(
    run_type="llm",
    name="openai_compatible_chat",
    process_inputs=_trace_inputs,
    _invocation_params_fn=_invocation_params,
)
def call_llm_api(cfg: dict, system_prompt: str, user_message: str,
                 max_tokens: int = 1024, temperature: float = 0.3,
                 run_tree=None) -> str:
    """调用 OpenAI 兼容的 LLM API。"""
    endpoint = cfg.get("endpoint", "")
    api_key = cfg.get("apiKey", "")
    model = cfg.get("model", "gpt-3.5-turbo")

    # 自动补全 /chat/completions 路径
    if endpoint and "/chat/completions" not in endpoint:
        endpoint = endpoint.rstrip("/") + "/chat/completions"

    print(f"[LLM] 正在调用 {endpoint[:50]}... model={model}", flush=True)
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode("utf-8")

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            usage = _usage_metadata(result, cfg)
            if run_tree is not None:
                trace_metadata = {
                    "endpoint_host": urlparse(endpoint).hostname or "",
                    "model": model,
                }
                if usage:
                    run_tree.set(metadata=trace_metadata, usage_metadata=usage)
                else:
                    run_tree.set(metadata=trace_metadata)
            print(f"[LLM] 响应状态: {resp.status}, body前200字: {raw[:200]}", flush=True)
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            reasoning = result.get("choices", [{}])[0].get("message", {}).get("reasoning_content", "")
            # 推理模型回答在 reasoning_content 中，去除思考过程头部
            if not content and reasoning:
                cleaned = reasoning.replace("Thinking Process:", "").strip()
                markers = ["Final Answer:", "最终回答:", "**Answer:**", "回答："]
                for marker in markers:
                    if marker in cleaned:
                        cleaned = cleaned.split(marker, 1)[1].strip()
                        break
                if cleaned and cleaned[0].isdigit():
                    parts = cleaned.split("\n\n")
                    cleaned = parts[-1] if len(parts) > 1 else cleaned
                content = cleaned
            elif not content:
                print(f"[LLM] content 和 reasoning_content 均为空", flush=True)
                print(f"[LLM] API 返回空内容，完整响应: {raw[:500]}", flush=True)
            return content
    except Exception as e:
        print(f"[LLM] API 调用失败: {e}", flush=True)
        raise RuntimeError(f"LLM API 调用失败: {e}")


# ═══════════════════ Embedding API ═══════════════════

def call_embedding_api(text: str, model: str = "") -> Optional[List[float]]:
    """调用 OpenAI 兼容的 /v1/embeddings 接口。

    从 LLM chat endpoint 自动推导 embedding endpoint。
    失败返回 None，不抛异常。
    """
    api_key = os.environ.get("EMBEDDING_API_KEY", "") or os.environ.get("LLM_API_KEY", "")
    endpoint = os.environ.get("EMBEDDING_ENDPOINT", "")
    if not endpoint:
        base = os.environ.get("LLM_ENDPOINT", "")
        if "/chat/completions" in base:
            endpoint = base.replace("/chat/completions", "/embeddings")
        elif base:
            endpoint = base.rstrip("/") + "/embeddings"
    if not endpoint:
        return None
    if not model:
        model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

    body = json.dumps({
        "input": text,
        "model": model,
    }).encode("utf-8")

    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            emb = result.get("data", [{}])[0].get("embedding", None)
            return emb
    except Exception as e:
        logger.warning("⚠️  Embedding API 调用失败: %s", e)
        return None
