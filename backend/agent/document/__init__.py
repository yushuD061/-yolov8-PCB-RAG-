"""文档领域模型与上传内容解析。"""

from agent.document.library import (
    DOCUMENT_SOURCE_AGENT,
    DOCUMENT_SOURCE_UPLOAD,
    DOCUMENT_STATUS_ACTIVE,
    Document,
    DocumentVersion,
    WriteRequest,
    WriteResult,
    new_id,
    normalize_write_request,
)
from agent.document.parser import ParseResult, parse_bytes

__all__ = [
    "DOCUMENT_SOURCE_AGENT",
    "DOCUMENT_SOURCE_UPLOAD",
    "DOCUMENT_STATUS_ACTIVE",
    "Document",
    "DocumentVersion",
    "WriteRequest",
    "WriteResult",
    "new_id",
    "normalize_write_request",
    "ParseResult",
    "parse_bytes",
]

