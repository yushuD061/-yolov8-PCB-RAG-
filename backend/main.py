"""
FastAPI 应用入口 — WebSocket 消息路由 + 生命周期管理 + 静态文件服务。
REST 路由已拆分到 routes/ 子目录，单例与目录集中在 app_state.py。
"""

import signal
signal.signal(signal.SIGABRT, signal.SIG_IGN)

import asyncio
import json
import os
import queue
import uuid
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import AlarmRecord
from app_state import (
    config_mgr, pipeline, alarm_store, history_store, inspection_store,
    UPLOAD_DIR, HLS_DIR, _CLASS_NAMES,
)
from routes import rag as rag_routes
from routes import detect as detect_routes
from routes import hls as hls_routes
from schemas import WSRequest, WSPushMessage


# ═══════════════════ 辅助方法 ═══════════════════

def _put_queue(q: queue.Queue, item):
    """非阻塞入队：满了就丢弃旧数据腾空间"""
    try:
        q.put_nowait(item)
    except queue.Full:
        try:
            q.get_nowait()
        except queue.Empty:
            pass
        try:
            q.put_nowait(item)
        except queue.Full:
            pass


# 前端字段 → 后端字段 翻译表（仅保留 PCB 相关）
_FRONTEND_TO_BACKEND = {
    "confidence": "detectionConfidence",
    "iouThreshold": "iouThreshold",
}

# 前端 WS 连接集合 — 板端帧到达时广播给所有前端
_frontend_clients: set[WebSocket] = set()


# ═══════════════════ 生命周期 ═══════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config_mgr.load()
    alarm_store.connect()
    history_store.connect()
    inspection_store.connect()
    pipeline.start(cfg)
    config_mgr.on_change(lambda c: pipeline.reconfigure(c))
    yield
    pipeline.stop()
    alarm_store.close()
    history_store.close()
    inspection_store.close()


app = FastAPI(title="PCB Defect Detection Backend", lifespan=lifespan)

# CORS — HLS (.m3u8 / .ts) 需要跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 REST 路由
app.include_router(rag_routes.router)
app.include_router(detect_routes.router)
app.include_router(hls_routes.router)


@app.get("/api/config")
async def get_config():
    return config_mgr.get().model_dump()


@app.patch("/api/config")
async def patch_config(request: dict):
    """持久化系统配置，供前端在 WebSocket 状态之外可靠更新。"""
    updated = config_mgr.update(request)
    maintenance = detect_routes.run_storage_maintenance(updated.retentionDays)
    return {"config": updated.model_dump(), "maintenance": maintenance}


# ═══════════════════ WebSocket 路由 ═══════════════════

@app.websocket("/ws")
async def ws_handler(ws: WebSocket):
    await ws.accept()
    print(f"[WS] 客户端已连接: {ws.client}")

    await ws.send_text(json.dumps(WSPushMessage(
        type="status_change",
        data={"connected": True},
    ).to_dict()))

    subscriptions: set[str] = {"telemetry", "video_frame"}
    pending_upload = None
    is_board = False  # 标记板端连接，不向其回传数据

    # 加入前端客户端集合（板端检测到后移除）
    _frontend_clients.add(ws)

    try:
        while True:
            sent = False

            if not is_board and "telemetry" in subscriptions:
                try:
                    data = pipeline.telemetry_queue.get_nowait()
                    if data is not None:
                        if "targets" in data:
                            await ws.send_text(json.dumps({
                                "type": "targets_stream",
                                "data": data["targets"],
                            }))
                        if "telemetry" in data:
                            tm = data["telemetry"]
                            await ws.send_text(json.dumps({
                                "type": "telemetry_metrics",
                                "data": {
                                    "fps": tm.get("fps", 0),
                                    "npu": tm.get("npuUtilization", 0),
                                    "cpu": tm.get("cpuUtilization", 0),
                                    "memUsed": tm.get("memoryUsed", 0),
                                    "memTotal": tm.get("memoryTotal", 4096),
                                    "temp": tm.get("socTemperature", 0),
                                    "latency": tm.get("inferenceLatency", 0),
                                    "selectedModel": tm.get("selectedModel", "pcb_model"),
                                },
                            }))
                        sent = True
                except queue.Empty:
                    pass

            if not is_board and "video_frame" in subscriptions and not sent:
                try:
                    jpeg_bytes = pipeline.frame_queue.get_nowait()
                    if jpeg_bytes is not None:
                        await ws.send_bytes(jpeg_bytes)
                        sent = True
                except queue.Empty:
                    pass

            if sent:
                continue

            try:
                msg_obj = await asyncio.wait_for(ws.receive(), timeout=0.02)
            except asyncio.TimeoutError:
                continue

            if msg_obj is None:
                break

            msg_type = msg_obj.get("type", "")

            if msg_type == "websocket.disconnect":
                print(f"[WS] 客户端断开: {ws.client}")
                break

            if msg_type == "websocket.receive" and "bytes" in msg_obj:
                chunk = msg_obj["bytes"]
                if pending_upload and isinstance(pending_upload, dict):
                    pending_upload["chunks"].append(chunk)
                else:
                    # 板端帧：广播给所有前端客户端（不走队列，避免多连接抢帧）
                    for client_ws in list(_frontend_clients):
                        try:
                            await client_ws.send_bytes(chunk)
                        except Exception:
                            pass
                    is_board = True
                    _frontend_clients.discard(ws)  # 板端自身不算前端
                continue

            if msg_type == "websocket.receive" and "text" in msg_obj:
                raw_text = msg_obj["text"]
            else:
                continue

            try:
                msg = json.loads(raw_text)
            except json.JSONDecodeError:
                await _send_error(ws, "", "", "无效的 JSON 格式")
                continue

            # ── 板端数据转发：targets_stream / telemetry_metrics → 广播给所有前端 ──
            msg_type_direct = msg.get("type", "")
            if msg_type_direct in ("targets_stream", "telemetry_metrics"):
                is_board = True
                _frontend_clients.discard(ws)  # 板端自身不算前端

                # targets_stream 同时存入告警记录，供 RAG 统计
                if msg_type_direct == "targets_stream":
                    targets_data = msg.get("data", [])
                    for t in targets_data:
                        alarm_store.append(AlarmRecord(
                            id=f"live-{int(time.time()*1000)}-{t.get('id','')}",
                            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
                            targetId=t.get("id", 0),
                            type=t.get("type", "defect"),
                            message=f"检测到 {t.get('className','未知')} 缺陷，置信度 {float(t.get('confidence',0))*100:.1f}%",
                        ))

                for client_ws in list(_frontend_clients):
                    try:
                        await client_ws.send_text(raw_text)
                    except Exception:
                        pass
                continue

            # ── 前端 WS 请求帧解析 ──
            req = WSRequest(
                id=msg.get("id", str(uuid.uuid4())),
                method=msg.get("method", ""),
                channel=msg.get("channel", ""),
                data=msg.get("data", {}),
            )

            # ── 消息路由 ──
            if req.method == "subscribe" and req.channel in ("telemetry", "video_frame"):
                subscriptions.add(req.channel)
                await _send_result(ws, req.id, req.channel, {"success": True})

            elif req.method == "CONF_UPDATE" or (req.method == "set" and req.channel == "config"):
                translated = {}
                for k, v in req.data.items():
                    backend_key = _FRONTEND_TO_BACKEND.get(k, k)
                    translated[backend_key] = v
                config_mgr.update(translated)
                await ws.send_text(json.dumps({
                    "type": "log_broadcast",
                    "data": {
                        "message": f"[INFO] 配置已更新: 模型 {req.data.get('selectedModel', '-')}, "
                                   f"保存 {req.data.get('saveResults', '-')}"
                    },
                }))

            elif req.method == "get" and req.channel == "config":
                cfg = config_mgr.get()
                await _send_result(ws, req.id, req.channel, cfg.model_dump())

            elif req.method == "list" and req.channel == "alarms":
                alarms = alarm_store.list()
                await _send_result(ws, req.id, req.channel,
                                   [a.model_dump() for a in alarms])

            elif req.method == "clear" and req.channel == "alarms":
                alarm_store.clear()
                await _send_result(ws, req.id, req.channel, {"success": True})

            elif req.method == "get" and req.channel == "history":
                history = history_store.get_7days()
                await _send_result(ws, req.id, req.channel,
                                   [h.to_dict() for h in history])

            elif req.method == "reset" and req.channel == "source":
                pipeline.video_source.reset()
                await _send_result(ws, req.id, req.channel, {"success": True})

            elif req.method == "switch" and req.channel == "source":
                source_type = req.data.get("sourceType", "rtsp")
                pipeline.video_source.reset()
                if source_type == "rtsp":
                    uri = req.data.get("rtspUrl", "")
                    if uri:
                        pipeline.video_source.open(uri, "rtsp")
                elif source_type in ("sample_image", "sample_video"):
                    pass
                await _send_result(ws, req.id, req.channel, {"success": True})

            elif req.method == "seek" and req.channel == "video:seek":
                seek_time = req.data.get("time", 0)
                pipeline.video_source.seek(seek_time)
                frame = pipeline.video_source.read()
                targets = []
                if frame is not None and pipeline.engine.loaded and pipeline.config:
                    try:
                        tracked = pipeline.engine.track(
                            frame,
                            conf_threshold=pipeline.config.detectionConfidence,
                            iou_threshold=pipeline.config.iouThreshold,
                        )
                        targets = [
                            {
                                "id": int(t.id),
                                "type": "defect",
                                "className": _CLASS_NAMES.get(t.class_id, f"class_{t.class_id}"),
                                "x": round(t.x, 2),
                                "y": round(t.y, 2),
                                "width": float(round(t.w, 2)),
                                "height": float(t.h, 2),
                                "confidence": float(round(t.confidence, 3)),
                            }
                            for t in tracked
                        ]
                    except Exception as e:
                        print(f"[Seek] 推理失败: {e}")
                await ws.send_text(json.dumps({
                    "id": req.id,
                    "type": "result",
                    "channel": "video:seek",
                    "data": {"success": True, "targets": targets},
                }))

            elif req.method == "upload":
                file_name = req.data.get("fileName", "upload")
                file_type = req.data.get("fileType", "")
                if file_type.startswith("image/"):
                    src_type = "sample_image"
                elif file_type.startswith("video/"):
                    src_type = "sample_video"
                else:
                    await _send_error(ws, req.id, "upload", "不支持的文件类型")
                    continue
                pending_upload = {
                    "fileName": file_name,
                    "fileType": file_type,
                    "srcType": src_type,
                    "chunks": [],
                    "msgId": req.id,
                }
                await _send_result(ws, req.id, "upload", {"ready": True})

            elif req.method == "upload:done":
                if pending_upload and isinstance(pending_upload, dict):
                    raw_bytes = b"".join(pending_upload["chunks"])
                    result = await _handle_upload_bytes(
                        raw_bytes,
                        pending_upload["fileName"],
                        pending_upload["fileType"],
                        pending_upload["srcType"],
                    )
                    pending_upload = None
                    await _send_result(ws, result["msgId"], "upload",
                                       {"success": result["success"]})
                else:
                    await _send_error(ws, req.id, "upload", "无待处理的上传")

            else:
                await _send_error(ws, req.id, req.channel,
                                  f"未知方法或频道: {req.method}/{req.channel}")

    except WebSocketDisconnect:
        print(f"[WS] 客户端已断开: {ws.client}")
    except Exception as e:
        print(f"[WS] 错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        _frontend_clients.discard(ws)


async def _send_result(ws: WebSocket, msg_id: str, channel: str, data: dict):
    await ws.send_text(json.dumps({
        "id": msg_id,
        "type": "result",
        "channel": channel,
        "data": data,
    }))


async def _send_error(ws: WebSocket, msg_id: str, channel: str, message: str):
    await ws.send_text(json.dumps({
        "id": msg_id,
        "type": "error",
        "channel": channel,
        "data": {"message": message},
    }))


async def _handle_upload_bytes(
    data: bytes, file_name: str, file_type: str, src_type: str
) -> dict:
    ext_map = {
        "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
        "video/mp4": ".mp4", "video/x-msvideo": ".avi",
    }
    ext = ext_map.get(file_type, os.path.splitext(file_name)[1] or ".bin")
    save_name = f"{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(data)
    try:
        pipeline.video_source.open(save_path, "video" if src_type == "sample_video" else "image")
        return {"msgId": "", "success": True}
    except Exception as e:
        print(f"[Upload] 打开文件失败: {e}")
        return {"msgId": "", "success": False, "error": str(e)}


# ═══════════════════ 简易端点 ═══════════════════

@app.get("/debug")
async def debug():
    return {
        "pipeline_running": pipeline._running,
        "pipeline_thread_alive": pipeline._thread.is_alive() if pipeline._thread else False,
        "engine_loaded": pipeline.engine.loaded,
        "video_source_opened": pipeline.video_source.is_opened,
        "video_source_type": pipeline.video_source.source_type,
        "telemetry_queue_size": pipeline.telemetry_queue.qsize(),
        "frame_queue_size": pipeline.frame_queue.qsize(),
        "model": pipeline.config.selectedModel if pipeline.config else None,
    }


@app.get("/debug/targets")
async def debug_targets():
    results = []
    try:
        q = pipeline.telemetry_queue
        while not q.empty():
            try:
                item = q.get_nowait()
                targets = item.get("targets", [])
                results.append(len(targets))
            except queue.Empty:
                break
        return {"samples": len(results), "target_counts": results,
                "has_targets": any(c > 0 for c in results)}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/health")
async def health():
    return {"status": "healthy", "timestamp": time.time()}


@app.get("/api/ping")
async def ping():
    return {"status": "ok", "message": "后端通信正常"}


# ═══════════════════ 静态文件服务 ═══════════════════

os.makedirs(HLS_DIR, exist_ok=True)
app.mount("/hls", StaticFiles(directory=os.path.abspath(HLS_DIR)), name="hls")

_WEB2_DIR = os.path.join(os.path.dirname(__file__), "..", "web2", "dist")
if os.path.isdir(_WEB2_DIR):
    assets_dir = os.path.join(_WEB2_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="web2_assets")
    app.mount("/", StaticFiles(directory=_WEB2_DIR, html=True), name="web2")
else:
    @app.get("/")
    async def dev_root():
        return HTMLResponse(
            "<h1>PCB Backend Running</h1>"
            "<p>Build frontend: <code>cd web2 && npm run build</code></p>"
            "<p>Dev mode: <code>cd web2 && npm run dev</code> (uses Vite proxy)</p>"
        )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=False)
