"""
RAG 路由 — 上传 / 问答 / 文档列表 / 删除 / 重建索引。
"""

from fastapi import APIRouter, UploadFile, File as FileParam

from app_state import alarm_store, inspection_store
from agent.document import parse_bytes
from agent.rag import get_rag_engine
from agent.config import get_agent_config
from services.llm_service import call_llm_api

router = APIRouter(tags=["rag"])


def _resolve_llm_cfg(llm_cfg: dict) -> dict:
    """优先前端配置，其次 .env，无效则返回空。"""
    if not llm_cfg or not llm_cfg.get("apiKey") or llm_cfg.get("apiKey") == "sk-your-api-key-here":
        ac = get_agent_config()
        if ac.llm_api_key and ac.llm_api_key != "sk-your-api-key-here":
            print(f"[RAG query] 降级使用 .env 配置")
            return {"endpoint": ac.llm_endpoint, "apiKey": ac.llm_api_key, "model": ac.llm_model}
    return llm_cfg or {}


@router.post("/api/rag/upload")
async def rag_upload(file: UploadFile = FileParam(...)):
    """解析上传文档并写入 RAG 知识库。支持 UTF-8/GBK 文本和 PDF。"""
    engine = get_rag_engine()
    try:
        content = await file.read()
        filename = file.filename or "未命名文档"

        parsed = parse_bytes(filename, file.content_type or "", content)
        count = engine.ingest(parsed.content, doc_name=filename)
        return {
            "success": True,
            "chunks": count,
            "name": filename,
            "parse": {
                "parser": parsed.parser,
                "contentType": parsed.content_type,
                "pages": parsed.pages,
                "textChars": parsed.text_chars,
                "needsOcr": parsed.needs_ocr,
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/api/rag/query")
async def rag_query(request: dict):
    """RAG 检索问答。body: {question: "...", llm: {endpoint, apiKey, model}}"""
    engine = get_rag_engine()
    question = request.get("question", "")
    if not question.strip():
        return {"answer": "请输入问题。", "sources": []}

    llm_cfg = request.get("llm", {})
    print(f"[RAG query] 前端 llm 配置: endpoint={llm_cfg.get('endpoint','')[:40]}... "
          f"key={'***' if llm_cfg.get('apiKey') else '无'}", flush=True)

    resolved = _resolve_llm_cfg(llm_cfg)
    print(f"[RAG query] 前端 key={'有' if llm_cfg.get('apiKey') else '无'} -> resolved key={'有' if resolved.get('apiKey') else '无'}", flush=True)

    if resolved and resolved.get("apiKey") and \
            resolved.get("apiKey") != "sk-your-api-key-here" and resolved.get("endpoint"):
        llm_fn = lambda sys, usr: call_llm_api(resolved, sys, usr)
        engine.set_generate_fn(llm_fn)
        if get_agent_config().rag_reranker_enabled:
            engine.set_reranker(llm_fn)
        else:
            engine._reranker = None
        engine.set_rewriter(llm_fn)
        print(f"[RAG query] LLM 已启用: {resolved.get('model')} "
              f"endpoint={resolved.get('endpoint','')[:50]}", flush=True)
    else:
        print(f"[RAG query] 无有效 LLM 配置，降级为检索摘要", flush=True)

    # 构建检测批次统计上下文。良品率必须基于完整批次，而不是缺陷告警条数。
    stats = inspection_store.stats()
    legacy_alarms = alarm_store.stats()
    extra_ctx = ""
    if stats.total_inspected > 0:
        type_distribution = ", ".join(
            f"{name} {count}处" for name, count in stats.by_type.items()
        ) or "无缺陷"
        source_distribution = ", ".join(
            f"{name} {count}次" for name, count in stats.by_source.items()
        )
        extra_ctx = (
            "【系统检测历史实时统计】"
            f"检测总数 {stats.total_inspected} 块；"
            f"良品 {stats.good_count} 块；不良品 {stats.defective_count} 块；"
            f"良品率 {stats.yield_rate * 100:.2f}%；"
            f"不良率 {stats.defect_rate * 100:.2f}%；"
            f"缺陷总数 {stats.total_defects} 处；"
            f"缺陷类型分布：{type_distribution}；"
            f"检测来源：{source_distribution}；"
            f"统计时间范围：{stats.first_at} 至 {stats.last_at}。"
            "以上良品率按无缺陷检测批次/检测总批次计算。"
        )
    elif legacy_alarms.total > 0:
        extra_ctx = (
            f"【旧版缺陷历史】存在 {legacy_alarms.total} 条缺陷告警，但没有检测总批次数，"
            "因此不能可靠计算良品率；只能分析缺陷类型分布："
            + ", ".join(f"{name} {count}处" for name, count in legacy_alarms.by_type.items())
            + "。"
        )

    answer, sources = engine.query(question, extra_context=extra_ctx)

    print(f"[RAG query] 检索到 {len(sources)} 条，答案长度 {len(answer)}，"
          f"检测批次 {stats.total_inspected} 条", flush=True)
    return {"answer": answer, "sources": sources}


@router.get("/api/rag/documents")
async def rag_documents():
    """获取已入库文档列表。"""
    engine = get_rag_engine()
    return {"documents": engine.store.get_docs()}


@router.delete("/api/rag/documents/{doc_id}")
async def rag_delete(doc_id: str):
    """删除指定文档（SQLite + PG 同步）。"""
    engine = get_rag_engine()
    try:
        deleted = engine.delete_doc(doc_id)
        return {"success": True, "deleted": deleted}
    except Exception as exc:
        return {"success": False, "error": str(exc), "documentId": doc_id}


@router.post("/api/rag/reindex")
async def rag_reindex():
    """强制重建 TF-IDF 索引（切换分词器后需要）。"""
    engine = get_rag_engine()
    engine._dirty = True
    engine._ensure_tfidf()
    return {"success": True, "chunks": engine.store.chunk_count()}
