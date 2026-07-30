"""从用户确认的四份公开 PCB PDF 生成可审计的 RAG 评估 CSV。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tiktoken
from dotenv import load_dotenv
from pypdf import PdfReader


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SOURCE_DIR = SCRIPT_DIR / "candidate_documents"
OUTPUT_PATH = SCRIPT_DIR / "pcb_nasa_evaluation.csv"
AUDIT_PATH = SCRIPT_DIR / "pcb_nasa_evaluation_audit.json"
BACKEND_DIR = PROJECT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(SCRIPT_DIR / ".env.ragas")
from services.llm_service import call_llm_api  # noqa: E402


SOURCES = [
    {
        "code": "PCB01",
        "file": "NASA_GSFC-STD-8001_Printed_Circuit_Board_QA.pdf",
        "name": "GSFC-STD-8001 Standard Quality Assurance Requirements for Printed Circuit Boards",
        "max_samples": 14,
    },
    {
        "code": "PCB02",
        "file": "NASA_PCB_Inspection_and_Quality_Control.pdf",
        "name": "Printed Circuit Board Inspection and Quality Control - PCB Failure Causes and Cures",
        "max_samples": 14,
    },
    {
        "code": "PCB03",
        "file": "NASA_PCB_Quality_Metrics_that_Drive_Reliability.pdf",
        "name": "PCB Quality Metrics that Drive Reliability",
        "max_samples": 12,
    },
    {
        "code": "PCB04",
        "file": "NASA_Value_of_Workmanship_Standards.pdf",
        "name": "The Value of Workmanship Standards",
        "max_samples": 8,
    },
]

MAX_CHARS = 1800
MAX_TOKENS = 480
MIN_CHARS = 260
ENCODING = tiktoken.get_encoding("cl100k_base")


@dataclass
class Chunk:
    chunk_id: str
    source_code: str
    source_name: str
    page_start: int
    page_end: int
    content: str

    @property
    def token_count(self) -> int:
        return len(ENCODING.encode(self.content))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate PCB NASA evaluation dataset")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=4)
    return parser.parse_args()


def clean_page(text: str) -> str:
    text = text.replace("\u00ad", "").replace("\xa0", " ")
    patterns = [
        r"Bhanu Sood, NASA GSFC \([^)]*\)",
        r"bhanu\.sood@nasa\.gov",
        r"IPC APEX EXPO 2020",
        r"February 3rd, 2020",
        r"August 8th and 9th, 2018",
        r"Check the GSFC Technical Standards Program website at .*?correct version prior to use\.?",
    ]
    for pattern in patterns:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"(?<!\w)\d{1,3}(?=\s)", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_units(text: str) -> list[str]:
    # 保留完整句子和项目符号语义，避免在缩写或数值中间硬切。
    units = re.split(r"(?<=[.!?;:])\s+(?=[A-Z0-9•\-])|\s+[•▪]\s+", text)
    output: list[str] = []
    for raw in units:
        unit = raw.strip(" -•▪")
        if len(unit) < 25:
            continue
        if len(unit) <= MAX_CHARS and len(ENCODING.encode(unit)) <= MAX_TOKENS:
            output.append(unit)
            continue
        # 表格抽取或缺少标点时可能形成超长单元；按单词边界硬切，绝不超窗。
        current: list[str] = []
        for word in unit.split():
            candidate = " ".join(current + [word])
            if current and (
                len(candidate) > MAX_CHARS
                or len(ENCODING.encode(candidate)) > MAX_TOKENS
            ):
                output.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            output.append(" ".join(current))
    return output


def chunk_pages(source: dict[str, Any]) -> list[Chunk]:
    reader = PdfReader(str(SOURCE_DIR / source["file"]))
    raw: list[tuple[int, str]] = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = clean_page(page.extract_text() or "")
        if len(text) >= MIN_CHARS:
            raw.append((page_no, text))

    chunks: list[Chunk] = []
    serial = 1
    for page_no, text in raw:
        units = split_units(text)
        current: list[str] = []
        for unit in units:
            candidate = " ".join(current + [unit])
            if current and (
                len(candidate) > MAX_CHARS
                or len(ENCODING.encode(candidate)) > MAX_TOKENS
            ):
                content = " ".join(current).strip()
                if len(content) >= MIN_CHARS:
                    chunks.append(
                        Chunk(
                            chunk_id=f"{source['code']}-P{page_no:03d}-C{serial:03d}",
                            source_code=source["code"],
                            source_name=source["name"],
                            page_start=page_no,
                            page_end=page_no,
                            content=content,
                        )
                    )
                    serial += 1
                current = [unit]
            else:
                current.append(unit)
        content = " ".join(current).strip()
        if len(content) >= MIN_CHARS:
            chunks.append(
                Chunk(
                    chunk_id=f"{source['code']}-P{page_no:03d}-C{serial:03d}",
                    source_code=source["code"],
                    source_name=source["name"],
                    page_start=page_no,
                    page_end=page_no,
                    content=content,
                )
            )
            serial += 1
    return select_representative(chunks, int(source["max_samples"]))


def select_representative(chunks: list[Chunk], limit: int) -> list[Chunk]:
    """按页面区间均匀抽样，跳过目录/封面式低信息块。"""
    informative = [
        chunk
        for chunk in chunks
        if chunk.token_count >= 90
        and not re.search(r"table of contents|agenda|biography|acknowledg", chunk.content, re.I)
    ]
    if len(informative) <= limit:
        return informative
    selected: list[Chunk] = []
    for index in range(limit):
        pos = round(index * (len(informative) - 1) / max(1, limit - 1))
        selected.append(informative[pos])
    return list({chunk.chunk_id: chunk for chunk in selected}.values())


def llm_config() -> dict[str, str]:
    return {
        "endpoint": os.getenv("JUDGE_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        "apiKey": os.getenv("JUDGE_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        "model": os.getenv("JUDGE_MODEL", os.getenv("OPENAI_MODEL", "")),
    }


def extract_json(raw: str) -> Any:
    value = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", value):
            try:
                parsed, _ = decoder.raw_decode(value[match.start() :])
                return parsed
            except json.JSONDecodeError:
                continue
    raise ValueError(f"模型输出不是合法 JSON: {value[:300]}")


def generate_batch(batch: list[Chunk], config: dict[str, str]) -> list[dict[str, Any]]:
    payload = [
        {
            "chunk_id": chunk.chunk_id,
            "source": chunk.source_name,
            "page": chunk.page_start,
            "content": chunk.content,
        }
        for chunk in batch
    ]
    system = (
        "你是 PCB/PCBA 评估数据集编辑。只依据输入的公开文档片段生成中文问答，禁止使用外部知识。"
        "每个片段生成恰好一条记录。问题必须能由该片段直接回答，避免询问作者、日期、页码等元数据；"
        "参考答案应简洁完整，通常 1-3 句，不复制整段；title 用英文或中文短标题；keywords 为 4-8 个中英文关键词。"
        "如果片段缺少可验证的技术事实，设置 usable=false。"
        "只输出严格 JSON 数组，每项字段为 chunk_id, usable, title, keywords, question_predict, reference_answer。"
    )
    raw = call_llm_api(
        config,
        system,
        json.dumps(payload, ensure_ascii=False),
        max_tokens=4096,
        temperature=0.0,
    )
    parsed = extract_json(raw)
    if not isinstance(parsed, list):
        raise ValueError("模型输出必须是 JSON 数组")
    return parsed


def validate_and_write(chunks: list[Chunk], generated: list[dict[str, Any]]) -> None:
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    rows: list[dict[str, str]] = []
    seen_questions: set[str] = set()
    for item in generated:
        chunk_id = str(item.get("chunk_id", ""))
        chunk = by_id.get(chunk_id)
        if chunk is None or item.get("usable") is False:
            continue
        question = str(item.get("question_predict", "")).strip()
        answer = str(item.get("reference_answer", "")).strip()
        if not question or not answer or question in seen_questions:
            continue
        # PDF 字体编码可能丢失数字或引号；此类片段不能进入黄金数据集。
        if re.search(r"[䇾䇿�]", chunk.content):
            continue
        if re.search(r"\$\d{1,2},\s*(?:per|/)", chunk.content, re.I):
            continue
        if len(question) > 120 or len(answer) > 600:
            continue
        seen_questions.add(question)
        keywords = item.get("keywords", [])
        if isinstance(keywords, list):
            keywords = ", ".join(str(value).strip() for value in keywords if str(value).strip())
        rows.append(
            {
                "chunk_id": chunk.chunk_id,
                "hierarchy": f"{chunk.source_name} > Page {chunk.page_start}",
                "title": str(item.get("title", "")).strip(),
                "content": chunk.content,
                "keywords": str(keywords).strip(),
                "question_predict": question,
                "relevant_doc_ids": json.dumps([chunk.chunk_id], ensure_ascii=False),
                "reference_answer": answer,
            }
        )

    columns = [
        "chunk_id",
        "hierarchy",
        "title",
        "content",
        "keywords",
        "question_predict",
        "relevant_doc_ids",
        "reference_answer",
    ]
    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    audit = {
        "source_files": [source["file"] for source in SOURCES],
        "selected_chunks": len(chunks),
        "written_rows": len(rows),
        "max_chars": max((len(row["content"]) for row in rows), default=0),
        "max_tokens_cl100k": max(
            (len(ENCODING.encode(row["content"])) for row in rows), default=0
        ),
        "rows_by_source": {
            source["code"]: sum(row["chunk_id"].startswith(source["code"]) for row in rows)
            for source in SOURCES
        },
        "output": str(OUTPUT_PATH),
    }
    AUDIT_PATH.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


def main() -> None:
    args = parse_args()
    chunks = [chunk for source in SOURCES for chunk in chunk_pages(source)]
    prepared = [
        {
            "chunk_id": chunk.chunk_id,
            "source": chunk.source_name,
            "page": chunk.page_start,
            "chars": len(chunk.content),
            "tokens_cl100k": chunk.token_count,
            "preview": chunk.content[:180],
        }
        for chunk in chunks
    ]
    (SCRIPT_DIR / "pcb_nasa_chunks_preview.json").write_text(
        json.dumps(prepared, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"已准备 {len(chunks)} 个候选块；最大 {max(c.token_count for c in chunks)} tokens")
    if args.prepare_only:
        return

    config = llm_config()
    if not all(config.values()):
        raise RuntimeError("缺少 JUDGE/OPENAI 模型配置")
    generated: list[dict[str, Any]] = []
    batch_size = max(1, args.batch_size)
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        print(f"生成问答 {start + 1}-{start + len(batch)}/{len(chunks)}")
        generated.extend(generate_batch(batch, config))
    validate_and_write(chunks, generated)


if __name__ == "__main__":
    main()
