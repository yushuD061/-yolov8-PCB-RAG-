"""
HLS 路由 — 启动 / 停止 / 状态查询。
"""

from fastapi import APIRouter

from core.hls_streamer import get_hls_streamer

router = APIRouter(prefix="/api/hls", tags=["hls"])


@router.post("/start")
async def hls_start(request: dict):
    """启动 RTSP → HLS 转换。body: {rtspUrl: "rtsp://..."}"""
    rtsp_url = request.get("rtspUrl", "")
    if not rtsp_url:
        return {"success": False, "error": "缺少 rtspUrl 参数"}
    streamer = get_hls_streamer()
    streamer.start(rtsp_url)
    if streamer.is_running:
        return {"success": True, "playlistUrl": "/hls/stream.m3u8"}
    else:
        return {"success": False, "error": streamer.status.get("error", "启动失败")}


@router.post("/stop")
async def hls_stop():
    """停止 HLS 转换并清理。"""
    streamer = get_hls_streamer()
    streamer.stop()
    return {"success": True}


@router.get("/status")
async def hls_status():
    """查询 HLS 转换状态。"""
    streamer = get_hls_streamer()
    return streamer.status