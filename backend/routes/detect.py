"""
检测路由 — 单图 YOLO 检测 / AI 预设报告 / 前端图片缺陷上报。
"""

import os
import time
import asyncio
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, UploadFile, File as FileParam, Form as FormParam

from app_state import (
    MODEL_DIR, DETECTION_RESULTS_DIR, config_mgr,
    alarm_store, inspection_store, _CLASS_NAMES,
)
from models import AlarmRecord
from services.llm_service import get_ai_preset

router = APIRouter(tags=["detect"])


def _cleanup_saved_images(retention_days: int) -> int:
    root = Path(DETECTION_RESULTS_DIR)
    if not root.exists():
        return 0
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    removed = 0
    for path in root.rglob("*.jpg"):
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
            if modified < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    for directory in sorted(root.glob("*"), reverse=True):
        if directory.is_dir():
            try:
                directory.rmdir()
            except OSError:
                pass
    return removed


def _save_detection_image(img, original_name: str, jpeg_quality: int) -> str:
    import cv2
    day = datetime.now().strftime("%Y-%m-%d")
    output_dir = Path(DETECTION_RESULTS_DIR) / day
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(original_name or "pcb").stem)[:80] or "pcb"
    filename = f"{datetime.now().strftime('%H%M%S')}_{uuid.uuid4().hex[:8]}_{stem}.jpg"
    path = output_dir / filename
    quality = max(50, min(100, int(jpeg_quality)))
    if not cv2.imwrite(str(path), img, [cv2.IMWRITE_JPEG_QUALITY, quality]):
        raise RuntimeError("检测图片保存失败")
    return str(path.relative_to(Path(DETECTION_RESULTS_DIR))).replace("\\", "/")


def run_storage_maintenance(retention_days: int) -> dict:
    """立即应用保留期到图片、检测批次和缺陷明细。"""
    return {
        "images": _cleanup_saved_images(retention_days),
        "inspections": inspection_store.prune(retention_days),
        "alarms": alarm_store.prune(retention_days),
    }


@router.post("/api/detect/image")
async def detect_image(
    file: UploadFile = FileParam(...),
    confidence: str = FormParam("0.25"),
    iou: str = FormParam("0.45"),
):
    """上传 PCB 图片 → YOLO 检测 → 返回缺陷列表"""
    import numpy as np
    import cv2

    conf_th = float(confidence)
    iou_th = float(iou)

    content = await file.read()
    img_array = np.frombuffer(content, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "无法解码图片"}

    cfg = config_mgr.get()
    model_path = os.path.join(MODEL_DIR, f"{cfg.selectedModel}.pt")
    if not os.path.exists(model_path):
        return {"error": f"模型文件不存在: {model_path}"}

    h_orig, w_orig = img.shape[:2]

    # 在独立线程中执行 YOLO 推理，避免阻塞事件循环
    def _infer():
        from ultralytics import YOLO
        model = YOLO(model_path)
        actual_names: dict = model.names if hasattr(model, 'names') else {}
        results = model(img, conf=conf_th, iou=iou_th, verbose=False)
        return results, actual_names

    loop = asyncio.get_event_loop()
    results, actual_names = await loop.run_in_executor(None, _infer)

    detections = []
    if results and len(results) > 0 and results[0].boxes is not None:
        boxes = results[0].boxes
        xyxy = boxes.xyxy.cpu().numpy()
        cls_ids = boxes.cls.int().cpu().numpy() if boxes.cls is not None else []
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else []

        for i in range(len(xyxy)):
            x1, y1, x2, y2 = xyxy[i]
            cid = int(cls_ids[i]) if i < len(cls_ids) else 0
            class_name = actual_names.get(cid, _CLASS_NAMES.get(cid, f"class_{cid}"))

            detections.append({
                "class_id": cid,
                "className": class_name,
                "type": "defect",
                "confidence": float(round(float(confs[i]), 3)) if i < len(confs) else 0.0,
                "x1": float(round(float(x1) / w_orig * 100, 2)),
                "y1": float(round(float(y1) / h_orig * 100, 2)),
                "x2": float(round(float(x2) / w_orig * 100, 2)),
                "y2": float(round(float(y2) / h_orig * 100, 2)),
                "width": float(round(float(x2 - x1) / w_orig * 100, 2)),
                "height": float(round(float(y2 - y1) / h_orig * 100, 2)),
            })

    storage = {"saved": False, "image": None, "jpegQuality": cfg.jpegQuality}
    if cfg.saveResults:
        storage["image"] = _save_detection_image(img, file.filename or "pcb", cfg.jpegQuality)
        storage["saved"] = True
        run_storage_maintenance(cfg.retentionDays)

    return {
        "detections": detections,
        "storage": storage,
        "debug": {"model": cfg.selectedModel, "conf": conf_th, "iou": iou_th, "classes": actual_names},
    }


@router.post("/api/gemini/analyze")
async def gemini_analyze(request: dict):
    """PCB 缺陷 AI 分析（预设报告）。"""
    return {"status": "ok", "report": get_ai_preset()}


@router.post("/api/alarms/report")
async def alarms_report(request: dict):
    """前端上报检测记录（图片检测等）供 RAG 统计分析。"""
    dets = request.get("detections", [])
    count = 0
    for d in dets:
        alarm_store.append(AlarmRecord(
            id=f"img-{int(time.time()*1000)}-{count}",
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            targetId=count,
            type="defect",
            message=f"检测到 {d.get('className','未知')} 缺陷，置信度 {float(d.get('confidence',0))*100:.1f}%",
        ))
        count += 1
    return {"success": True, "reported": count}


@router.post("/api/inspections/report")
async def inspections_report(request: dict):
    """记录一次完整 PCB 检测；零缺陷记录是计算良品率的必要样本。"""
    detections = request.get("detections", [])
    if not isinstance(detections, list):
        return {"success": False, "error": "detections 必须是数组"}
    cfg = config_mgr.get()
    if not cfg.saveResults:
        return {"success": True, "saved": False, "reason": "saveResults=false"}
    try:
        inspection_store.prune(cfg.retentionDays)
        alarm_store.prune(cfg.retentionDays)
        inspection_id = inspection_store.append(
            detections=detections,
            source=str(request.get("source") or "image"),
            item_name=str(request.get("itemName") or ""),
            batch_id=str(request.get("batchId") or ""),
            timestamp=request.get("timestamp"),
            inspection_id=request.get("id"),
        )
        # 同步缺陷明细，保留现有告警/RAG 缺陷类型统计能力。
        for index, detection in enumerate(detections):
            alarm_store.append(AlarmRecord(
                id=f"{inspection_id}-{index}",
                timestamp=request.get("timestamp") or time.strftime("%Y-%m-%d %H:%M:%S"),
                targetId=index,
                type="defect",
                message=(
                    f"检测到 {detection.get('className', '未知')} 缺陷，"
                    f"置信度 {float(detection.get('confidence', 0))*100:.1f}%"
                ),
            ))
        return {
            "success": True,
            "saved": True,
            "inspectionId": inspection_id,
            "isGood": len(detections) == 0,
            "defectCount": len(detections),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@router.get("/api/inspections/stats")
async def inspections_stats():
    """返回可用于质量分析的真实检测批次统计。"""
    return {
        "stats": inspection_store.stats().to_dict(),
        "recent": inspection_store.recent(20),
    }
