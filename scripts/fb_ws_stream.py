#!/usr/bin/env python3
"""
fb_ws_stream.py — RV1126B 板端：KMS 抓屏 + 官方程序 stdout 解析 → WebSocket 推流到 PC 后端。

自动启动官方 rknn_yolov8_cam 并解析其 stdout 检测结果，
同时用 ffmpeg kmsgrab 抓屏推 JPEG 帧。

用法:
  python3 fb_ws_stream.py --host 192.168.50.1 --port 5000
  python3 fb_ws_stream.py --host 192.168.50.1 --fps 10 --quality 8
  python3 fb_ws_stream.py --no-yolo   # 不启动官方程序（手动管理）
"""

import asyncio
import json
import re
import time
import argparse
import sys
import os
import signal
import websockets

from board_config import Detection, Target

# ── 命令行参数 ──
parser = argparse.ArgumentParser(description="KMS 抓屏 + YOLO 检测 → WS 推流")
parser.add_argument("--host", default="192.168.50.1", help="PC 后端 IP")
parser.add_argument("--port", type=int, default=5000, help="PC 后端端口")
parser.add_argument("--fps", type=int, default=5, help="截取帧率 (1-25)")
parser.add_argument("--quality", type=int, default=6,
                    help="JPEG 质量 2-31（越小画质越好）")
parser.add_argument("--model", default="model/yolov8_best.rknn", help="RKNN 模型路径")
parser.add_argument("--camera", type=int, default=31, help="摄像头索引")
parser.add_argument("--no-yolo", action="store_true", help="不启动官方程序（已手动运行）")
parser.add_argument("--no-rotate", action="store_true", help="不旋转画面")
args = parser.parse_args()

WS_URL = f"ws://{args.host}:{args.port}/ws"

# 画面尺寸（kmsgrab 原始输出，旋转前）
FB_W = 720
FB_H = 1280

# rotate 后的输出尺寸
if not args.no_rotate:
    OUT_W, OUT_H = FB_H, FB_W  # 1280 x 720
else:
    OUT_W, OUT_H = FB_W, FB_H

# ── 全局：最近一帧的检测结果 ──
latest_detections: list[Detection] = []
det_lock = asyncio.Lock()
frame_seq = 0


def parse_yolo_line(line: str) -> Detection | None:
    """
    解析官方 rknn_yolov8_cam 的 stdout 输出。
    已知格式: 'missing_hole @ (100 200 300 400) 0.853'
    也可能: 'missing_hole, (100,200,300,400), 0.853'
    """
    line = line.strip()
    if not line:
        return None

    # 格式 1: class_name @ (x1 y1 x2 y2) confidence
    m = re.match(r'(\S+)\s*@\s*\((\d+)\s+(\d+)\s+(\d+)\s+(\d+)\)\s*([\d.]+)', line)
    if m:
        return Detection(
            class_name=m.group(1),
            x1=int(m.group(2)), y1=int(m.group(3)),
            x2=int(m.group(4)), y2=int(m.group(5)),
            confidence=float(m.group(6)),
        )

    # 格式 2: class_name, (x1,y1,x2,y2), confidence
    m = re.match(r'(\S+)\s*[,@]\s*\((\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)\s*[, ]\s*(\d+)\)\s*[, ]\s*([\d.]+)', line)
    if m:
        return Detection(
            class_name=m.group(1),
            x1=int(m.group(2)), y1=int(m.group(3)),
            x2=int(m.group(4)), y2=int(m.group(5)),
            confidence=float(m.group(6)),
        )

    return None


def det_to_target(det: Detection, idx: int) -> Target:
    """将检测框坐标归一化到 0-100%（基于旋转后尺寸）"""
    x1, y1, x2, y2 = det.x1, det.y1, det.x2, det.y2

    if not args.no_rotate:
        # 顺时针 90°：(x, y) in 720x1280 → (1280-y, x) in 1280x720
        nx1 = (FB_H - y2) / FB_H * 100
        ny1 = x1 / FB_W * 100
        nx2 = (FB_H - y1) / FB_H * 100
        ny2 = x2 / FB_W * 100
    else:
        nx1 = x1 / FB_W * 100
        ny1 = y1 / FB_H * 100
        nx2 = x2 / FB_W * 100
        ny2 = y2 / FB_H * 100

    w = nx2 - nx1
    h = ny2 - ny1
    cx = nx1 + w / 2
    cy = ny1 + h / 2

    return Target(
        id=idx + 1,
        class_name=det.class_name,
        x=cx, y=cy, width=w, height=h,
        confidence=det.confidence,
    )


async def yolo_stdout_reader(proc, ws_list: list):
    """
    后台任务：读取官方程序 stdout → 解析检测结果 → 发送 targets_stream。
    ws_list 是可变列表 [ws_connection]，连接断开时清空。
    """
    global latest_detections, frame_seq
    buf = ""
    dets_this_frame: list[Detection] = []

    while True:
        line_bytes = await proc.stdout.readline()
        if not line_bytes:
            print("[YOLO] 官方程序 stdout 结束")
            return

        line = line_bytes.decode(errors="replace").strip()
        if not line:
            continue

        det = parse_yolo_line(line)
        if det:
            dets_this_frame.append(det)
        else:
            # 非检测行 — 可能是分隔符/日志。如果之前累积了检测结果，视为一帧结束
            if dets_this_frame:
                async with det_lock:
                    latest_detections = dets_this_frame
                    frame_seq += 1

                # 发送 targets_stream
                targets = [det_to_target(d, i) for i, d in enumerate(dets_this_frame)]
                msg = json.dumps({
                    "type": "targets_stream",
                    "data": [t.to_dict() for t in targets],
                })

                for ws in list(ws_list):
                    try:
                        await ws.send(msg)
                    except Exception:
                        pass

                dets_this_frame = []


async def extract_jpeg(stream: asyncio.StreamReader):
    """从 ffmpeg image2pipe 流中提取一帧完整 JPEG。"""
    buf = bytearray()
    while True:
        chunk = await stream.read(8192)
        if not chunk:
            return None
        buf.extend(chunk)

        while True:
            soi = buf.find(b"\xff\xd8")
            if soi == -1:
                buf.clear()
                break
            if soi > 0:
                del buf[:soi]
                soi = 0
            eoi = buf.find(b"\xff\xd9", 2)
            if eoi == -1:
                if len(buf) > 4 * 1024 * 1024:
                    print("[WARN] JPEG 缓冲区溢出，清空")
                    buf.clear()
                break
            jpeg = bytes(buf[:eoi + 2])
            del buf[:eoi + 2]
            if len(jpeg) > 1500:
                return jpeg


async def run_ffmpeg():
    """启动 ffmpeg 子进程：KMS/DRM 抓屏 → MJPEG → stdout pipe"""
    vf = "hwdownload,format=bgr0,format=yuv420p"
    if not args.no_rotate:
        vf += ",transpose=1"

    cmd = [
        "ffmpeg",
        "-f", "kmsgrab", "-i", "-",
        "-vf", vf,
        "-c:v", "mjpeg", "-q:v", str(args.quality),
        "-r", str(args.fps),
        "-f", "image2pipe",
        "-loglevel", "error",
        "-",
    ]
    print(f"[ffmpeg] {' '.join(cmd)}")
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )


async def run_yolo():
    """启动官方 rknn_yolov8_cam 子进程，返回 proc 或 None。"""
    cmd = ["./rknn_yolov8_cam", args.model, str(args.camera)]
    print(f"[YOLO] 启动: {' '.join(cmd)}")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,  # stderr 合并到 stdout
        )
        print(f"[YOLO] PID={proc.pid}")
        return proc
    except FileNotFoundError:
        print("[YOLO] 错误: 找不到 rknn_yolov8_cam，请确认在正确目录")
        return None
    except Exception as e:
        print(f"[YOLO] 启动失败: {e}")
        return None


async def ws_send_loop(ws, ffmpeg_proc, ws_list):
    """主循环：读帧 → 发 WS → 发遥测"""
    fc = 0
    tick = time.time()

    while True:
        jpeg = await extract_jpeg(ffmpeg_proc.stdout)
        if jpeg is None:
            print("[WARN] ffmpeg 输出中断")
            return False

        await ws.send(jpeg)
        fc += 1

        elapsed = time.time() - tick
        if elapsed >= 2.0:
            fps = fc / elapsed if elapsed > 0 else 0
            async with det_lock:
                ndet = len(latest_detections)

            await ws.send(json.dumps({
                "type": "telemetry_metrics",
                "data": {
                    "fps": round(fps, 1),
                    "npu": 0, "cpu": 0,
                    "memUsed": 0, "memTotal": 0,
                    "temp": 0, "latency": 0,
                    "selectedModel": "yolov8_best",
                    "defects": ndet,
                },
            }))
            print(f"[INFO] FPS={fps:.1f}  检出={ndet}  帧数={fc}")
            fc = 0
            tick = time.time()

    return True


async def main():
    global latest_detections

    rotate_info = "" if args.no_rotate else " (右旋90°)"
    print(f"[INFO] fb_ws_stream 启动")
    print(f"[INFO] 捕获: kmsgrab{rotate_info}  {args.fps}fps  JPEG q={args.quality}")
    print(f"[INFO] 输出: {OUT_W}x{OUT_H}")
    print(f"[INFO] 推流: {WS_URL}")

    # 启动官方程序
    yolo_proc = None
    yolo_task = None
    if not args.no_yolo:
        yolo_proc = await run_yolo()
        if yolo_proc is None:
            print("[WARN] 无法启动官方程序，将只推流不含检测数据")
    else:
        print("[INFO] --no-yolo: 跳过启动官方程序")

    # 启动 ffmpeg
    ffmpeg_proc = await run_ffmpeg()

    ws_list = []  # 当前 WS 连接（供 yolo_stdout_reader 使用）

    # 启动 stdout 解析任务
    if yolo_proc is not None:
        yolo_task = asyncio.create_task(yolo_stdout_reader(yolo_proc, ws_list))

    try:
        while True:
            try:
                print(f"[WS] 正在连接 {WS_URL} ...")
                async with websockets.connect(
                    WS_URL,
                    ping_interval=None,
                    open_timeout=10,
                    close_timeout=5,
                ) as ws:
                    ws_list.append(ws)
                    print(f"[WS] 已连接 → 开始推流")

                    ok = await ws_send_loop(ws, ffmpeg_proc, ws_list)

                    ws_list.remove(ws)
                    if not ok:
                        print("[INFO] 重启 ffmpeg ...")
                        ffmpeg_proc = await run_ffmpeg()

            except (websockets.exceptions.ConnectionClosed, OSError, ConnectionError) as e:
                print(f"[WS] 连接断开: {e}, 3 秒后重连...")
                await asyncio.sleep(3)
            except Exception as e:
                print(f"[ERR] {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)
    finally:
        if yolo_task:
            yolo_task.cancel()
        if yolo_proc:
            try:
                yolo_proc.terminate()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] 已停止")
