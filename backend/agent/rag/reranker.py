"""
LLM 精排器（Reranker）— 用一次 LLM listwise 调用对候选 chunk 精排。

用法：
    reranker = LLMReranker(generate_fn)
    reranked = reranker.rerank(query, results, top_k)

失败时自动回退原顺序，不中断流程。
"""

import json
import logging
import re
from typing import Any, Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# LLM 生成函数签名：fn(system_prompt, user_message) -> str
GenerateFn = Callable[[str, str], str]


class LLMReranker:
    """用一次 LLM listwise 调用对候选 chunk 精排，失败时回退原顺序。"""

    def __init__(self, generate_fn: Optional[GenerateFn], preview_len: int = 200):
        self.generate_fn = generate_fn
        self.preview_len = preview_len if preview_len > 0 else 200

    def rerank(self, query: str, results: List, top_k: int) -> List:
        """精排候选列表。

        参数：
            query:   用户问题
            results: 检索结果列表（元素需有 .score 和 .content / .chunk.content）
            top_k:   返回前 N 条
        返回：
            精排后的结果列表
        """
        if not results:
            return []
        if self.generate_fn is None or len(results) == 1:
            return _truncate(results, top_k)

        try:
            raw = self.generate_fn(
                self._system_prompt(),
                self._user_msg(query, results),
            )
            scores = _parse_scores(raw)
        except Exception as e:
            logger.warning("Rerank 失败，回退原顺序: %s", e)
            return _truncate(results, top_k)

        if not scores:
            return _truncate(results, top_k)

        # 构建 idx → LLM_score 映射
        score_map: dict[int, float] = {}
        for idx, score in scores:
            if 0 <= idx < len(results):
                score_map[idx] = score

        if len(score_map) != len(results):
            logger.warning(
                "Rerank scores 数量(%d) != 候选数量(%d)，缺失项补 0",
                len(score_map), len(results),
            )
            for i in range(len(results)):
                score_map.setdefault(i, 0.0)

        # 按 LLM 分 → TF-IDF 分降序排列
        ordered = []
        for idx, result in enumerate(results):
            llm_score = score_map.get(idx, 0.0)
            ordered.append((llm_score, getattr(result, "score", 0.0), idx, result))
        ordered.sort(key=lambda item: (item[0], item[1], -item[2]), reverse=True)

        # 更新原始结果的分值和来源标记
        out = []
        for llm_score, _rrf_score, _idx, result in ordered:
            if llm_score >= 0:
                result.score = llm_score / 10.0
            result.source = f"{getattr(result, 'source', '')}+rerank"
            out.append(result)
        return _truncate(out, top_k)

    # ── Prompt 构建 ──

    def _system_prompt(self) -> str:
        return (
            "你是检索系统的精排器。给定用户问题和若干候选段落（每条带编号 idx），"
            "判断每条段落对回答该问题的**相关性 + 信息密度**，给 0~10 的整数分。\n\n"
            "打分准则：\n"
            "- 10：直接回答了问题\n"
            "- 7~9：包含明确相关事实 / 线索\n"
            "- 4~6：弱相关 / 部分相关\n"
            "- 1~3：仅出现共现关键词，不能用来回答\n"
            "- 0：无关 / 噪声\n\n"
            "输出**严格 JSON**，不要任何说明文字、不要 markdown 代码块：\n"
            '{"scores": [{"idx": 0, "score": 9}, {"idx": 1, "score": 3}]}\n\n'
            "约束：\n"
            "- scores 数量严格等于候选数量\n"
            "- score 是 0~10 的整数\n"
            "- 不依赖你自己的知识，只看给出的段落"
        )

    def _user_msg(self, query: str, results: List) -> str:
        lines = [f"用户问题：{query}", "", "候选段落："]
        for idx, result in enumerate(results):
            content = _result_content(result)
            if len(content) > self.preview_len:
                content = content[:self.preview_len] + "..."
            lines.append(f"[{idx}] {content}")
        return "\n".join(lines)


# ═══════════════════ 辅助函数 ═══════════════════


def _result_content(result: Any) -> str:
    """从检索结果中提取文本内容（兼容不同数据结构）。"""
    if hasattr(result, "content"):
        return str(result.content)
    chunk = getattr(result, "chunk", None)
    if chunk is not None:
        # 检索命中的是子块，但回答使用父块；精排也必须看到同一份完整语义。
        parent = getattr(chunk, "parent_content", "")
        if parent:
            return str(parent)
        if hasattr(chunk, "content"):
            return str(chunk.content)
    return ""


def _parse_scores(raw: str) -> List[Tuple[int, float]]:
    """解析 LLM 返回的 JSON 评分结果。"""
    raw = _strip_json_fence(raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = data.get("scores", []) if isinstance(data, dict) else []
    scores: List[Tuple[int, float]] = []
    for item in items:
        try:
            scores.append((int(item.get("idx")), float(item.get("score"))))
        except Exception:
            continue
    return scores


def _strip_json_fence(raw: str) -> str:
    """去除 LLM 可能输出的 markdown 代码围栏。"""
    raw = (raw or "").strip()
    raw = re.sub(r"^```json\s*", "", raw)
    raw = re.sub(r"^```\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return raw.strip()


def _truncate(results: List, top_k: int) -> List:
    """截断列表至前 top_k 项。"""
    if top_k > 0 and len(results) > top_k:
        return results[:top_k]
    return results
