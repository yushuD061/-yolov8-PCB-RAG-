"""将上传的文本或 PDF 字节解析为适合 RAG 切分的规范文本。"""

import io
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


MIN_USEFUL_PDF_TEXT_RUNES = 80
_HYPHEN_LINE_BREAK_RE = re.compile(r"([A-Za-z])-\n([A-Za-z])")


@dataclass
class ParseResult:
    filename: str = ""
    content_type: str = ""
    parser: str = ""
    content: str = ""
    pages: int = 0
    text_chars: int = 0
    needs_ocr: bool = False


def parse_bytes(filename: str, content_type: str, data: bytes) -> ParseResult:
    filename = filename or ""
    content_type = _normalize_content_type(filename, content_type)
    ext = Path(filename).suffix.lower()
    if content_type == "application/pdf" or ext == ".pdf":
        return _parse_pdf(filename, content_type, data)

    text = _normalize_text(_decode_text(data))
    if not text.strip():
        raise ValueError("上传的文档为空")
    return ParseResult(
        filename=filename,
        content_type=content_type,
        parser="plain_text",
        content=text,
        text_chars=len(text),
    )


def _parse_pdf(filename: str, content_type: str, data: bytes) -> ParseResult:
    extractors = (
        _extract_pdf_with_pdfplumber,
        _extract_pdf_with_pypdf,
        _extract_pdf_with_pdftotext,
    )
    for extractor in extractors:
        text, pages, parser_name = extractor(data)
        if text.strip():
            text = _normalize_text(text)
            chars = len(text)
            return ParseResult(
                filename=filename,
                content_type=content_type,
                parser=parser_name,
                content=text,
                pages=pages,
                text_chars=chars,
                needs_ocr=pages > 0 and chars < MIN_USEFUL_PDF_TEXT_RUNES,
            )
    raise ValueError("PDF 没有可提取文本，需要先执行 OCR")


def _extract_pdf_with_pdfplumber(data: bytes) -> Tuple[str, int, str]:
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return "", 0, "pdfplumber"
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as file:
            file.write(data)
            path = file.name
        try:
            texts = []
            with pdfplumber.open(path) as pdf:
                pages = len(pdf.pages)
                for index, page in enumerate(pdf.pages, 1):
                    text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
                    if text.strip():
                        texts.append(f"--- page {index} ---\n{text}")
            return "\n\n".join(texts), pages, "pdfplumber"
        finally:
            _safe_unlink(path)
    except Exception:
        return "", 0, "pdfplumber"


def _extract_pdf_with_pypdf(data: bytes) -> Tuple[str, int, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", 0, "pypdf"
    try:
        reader = PdfReader(io.BytesIO(data))
        texts = []
        for index, page in enumerate(reader.pages, 1):
            text = page.extract_text() or ""
            if text.strip():
                texts.append(f"--- page {index} ---\n{text}")
        return "\n\n".join(texts), len(reader.pages), "pypdf"
    except Exception:
        return "", 0, "pypdf"


def _extract_pdf_with_pdftotext(data: bytes) -> Tuple[str, int, str]:
    executable = shutil.which("pdftotext")
    if not executable:
        return "", 0, "pdftotext"
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as file:
            file.write(data)
            path = file.name
        try:
            output = subprocess.check_output(
                [executable, "-layout", "-enc", "UTF-8", path, "-"],
                timeout=30,
            )
            return output.decode("utf-8", errors="ignore"), 0, "pdftotext"
        finally:
            _safe_unlink(path)
    except Exception:
        return "", 0, "pdftotext"


def _normalize_content_type(filename: str, content_type: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized:
        return normalized
    guessed, _ = mimetypes.guess_type(filename or "")
    return (guessed or "text/plain").lower()


def _decode_text(data: bytes) -> str:
    for encoding in ("utf-8", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法解码文件，请上传 UTF-8/GBK 文本或 PDF")


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\x00", "")
    text = _HYPHEN_LINE_BREAK_RE.sub(r"\1\2", text)
    normalized = "\n".join(line.rstrip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _safe_unlink(path: Optional[str]) -> None:
    if not path:
        return
    try:
        os.remove(path)
    except OSError:
        pass

