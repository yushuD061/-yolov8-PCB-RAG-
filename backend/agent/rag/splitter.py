"""
文本切分器 — 递归分隔符栈 + Markdown 保护 + 尾部重叠。

提供 RecursiveSplitter 类，可按段落 → 句子 → 固定长度递归切分，
同时保护 Markdown 代码块不被切开，并将相邻标题行与正文合并。
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# ═══════════════════ 默认分隔符优先级 ═══════════════════
# 从粗到细依次尝试，空字符串 "" 表示固定长度硬切
_DEFAULT_SEPARATORS: List[str] = ["\n\n", "\n", "。", "！", "？", "；", " ", ""]

# Markdown 围栏（``` 或 ~~~）
_FENCE_RE = re.compile(
    r"^(```|~~~)[^\n]*\n.*?^\1[ \t]*$\n?",
    re.MULTILINE | re.DOTALL,
)

_HEADING_RE = re.compile(r"^#{1,6} ")


@dataclass
class Chunk:
    """切分结果单元。"""
    id: int
    content: str


class RecursiveSplitter:
    """递归分隔符栈文本切分器。

    策略：
    1. 保护 Markdown 围栏（``` / ~~~）使其不被切开；
    2. 按分隔符列表优先级递归切分；
    3. 将孤立的标题行与后续段落合并；
    4. 对尾部应用 overlap。

    参数：
        chunk_size:     目标块大小（字符数），默认 500
        chunk_overlap:  相邻块之间的重叠字符数，默认 50
        separators:     分隔符优先级列表，默认中/英文标点
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50,
                 separators: Optional[List[str]] = None):
        self.chunk_size = max(1, int(chunk_size or 1))
        overlap = max(0, int(chunk_overlap or 0))
        if overlap >= self.chunk_size:
            overlap = self.chunk_size - 1
        self.chunk_overlap = overlap
        self.separators = list(separators) if separators else list(_DEFAULT_SEPARATORS)

    # ── 公开接口 ──

    def split(self, text: str) -> List[Chunk]:
        """切分文本，返回带 id 的 Chunk 列表。"""
        if not text:
            return []

        # 1. 保护围栏
        atoms = self._protect_fences(text)

        # 2. 对非围栏部分递归切分
        pieces: List[Tuple[bool, str]] = []
        for is_atom, segment in atoms:
            if is_atom:
                pieces.append((True, segment))
                continue
            for p in self._recursive_split(segment, self.separators):
                pieces.append((False, p))

        # 3. 合并（标题行与正文合并，小段合并到大段）
        merged = self._merge(pieces)

        # 4. 尾部重叠
        merged = self._apply_overlap(merged)

        return [Chunk(id=i, content=c) for i, c in enumerate(merged)]

    def split_text(self, text: str) -> List[str]:
        """兼容旧接口：返回纯文本列表。"""
        return [c.content for c in self.split(text)]

    # ── Markdown 围栏保护 ──

    @staticmethod
    def _protect_fences(text: str) -> List[Tuple[bool, str]]:
        """将 Markdown 代码/公式围栏标记为原子块（True），不允许切开。"""
        atoms: List[Tuple[bool, str]] = []
        cursor = 0
        for m in _FENCE_RE.finditer(text):
            if m.start() > cursor:
                atoms.append((False, text[cursor:m.start()]))
            atoms.append((True, m.group(0)))
            cursor = m.end()
        if cursor < len(text):
            atoms.append((False, text[cursor:]))
        if not atoms:
            atoms = [(False, text)]
        return atoms

    # ── 递归切分 ──

    def _recursive_split(self, text: str, seps: List[str]) -> List[str]:
        """按分隔符栈递归切分，直到每段 <= chunk_size。"""
        if len(text) <= self.chunk_size:
            return [text] if text.strip() else []

        if not seps:
            return self._hard_split(text)

        sep = seps[0]
        rest = seps[1:]

        if sep == "":
            return self._hard_split(text)

        parts = self._split_keep_sep(text, sep)

        # 没切出来（文本里没有该分隔符）：降级到下一个分隔符
        if len(parts) <= 1 and parts and parts[0] == text:
            return self._recursive_split(text, rest)

        out: List[str] = []
        for p in parts:
            if not p:
                continue
            if len(p) <= self.chunk_size:
                if p.strip():
                    out.append(p)
            else:
                out.extend(self._recursive_split(p, rest))
        return out

    @staticmethod
    def _split_keep_sep(text: str, sep: str) -> List[str]:
        """按分隔符切分，将分隔符保留在后续片段开头（类似 LangChain 风格）。"""
        if sep == "":
            return [text]
        parts = text.split(sep)
        if len(parts) <= 1:
            return parts
        out = [parts[0]]
        for p in parts[1:]:
            out.append(sep + p)
        return out

    def _hard_split(self, text: str) -> List[str]:
        """定长硬切（最后的回退方案）。"""
        out: List[str] = []
        size = self.chunk_size
        for i in range(0, len(text), size):
            piece = text[i:i + size]
            if piece:
                out.append(piece)
        return out

    # ── 合并 ──

    def _merge(self, pieces: List[Tuple[bool, str]]) -> List[str]:
        """合并小片段至不超过 chunk_size，同时将孤立的标题行与后续正文合并。"""
        merged: List[str] = []
        buf = ""
        buf_heading_only = False

        def is_heading_only(s: str) -> bool:
            stripped = s.strip()
            if not stripped or "\n" in stripped:
                return False
            return bool(_HEADING_RE.match(stripped))

        for is_atom, p in pieces:
            if not p:
                continue

            # 缓冲区为空 → 直接拿
            if not buf:
                buf = p
                buf_heading_only = (not is_atom) and is_heading_only(p)
                continue

            # 缓冲区只包含标题 → 不管长度强制追加（标题不应该独立成块）
            if buf_heading_only:
                buf = buf + p
                buf_heading_only = (not is_atom) and is_heading_only(buf)
                continue

            # 原子块（围栏）：不能拆分
            if is_atom:
                if len(buf) + len(p) <= self.chunk_size:
                    buf = buf + p
                    buf_heading_only = False
                    continue
                merged.append(buf)
                buf = p
                buf_heading_only = False
                continue

            # 非原子块：在长度允许内合并
            if len(buf) + len(p) <= self.chunk_size:
                buf = buf + p
                buf_heading_only = is_heading_only(buf)
                continue

            merged.append(buf)
            buf = p
            buf_heading_only = is_heading_only(p)

        if buf:
            merged.append(buf)
        return merged

    # ── 尾部重叠 ──

    def _apply_overlap(self, merged: List[str]) -> List[str]:
        """将前一块的末尾字符作为后一块的前缀，实现 context 衔接。"""
        if self.chunk_overlap <= 0 or len(merged) <= 1:
            return merged
        out = [merged[0]]
        n = self.chunk_overlap
        for i in range(1, len(merged)):
            prev = merged[i - 1]
            tail = prev[-n:] if len(prev) >= n else prev
            out.append(tail + merged[i])
        return out
