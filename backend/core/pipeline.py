"""
推理管线 — 后台线程主循环：取帧 → YOLO track → 推送。
PCB 缺陷检测：仅检测+追踪，无速度/车距估算，无轨迹线绘制。
"""

import asyncio
import time
import threading
import os
import queue

import cv2
from models import SystemConfig
from core.yolo_engine import YoloEngine
from core.video_source import VideoSource
from core.hardware import HardwareCollector

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_MODEL_DIR = os.path.join(_PROJECT_ROOT, "model")

# 6 类 PCB 缺陷类别名称映射
_CLASS_NAMES = {
    0: "missing_hole",
    1: "mouse_bite",
    2: "open_circuit",
    3: "short",
    4: "spur",
    5: "spurious_copper",
}


class Pipeline:
    def __init__(self):
        self._running = False
        self._thread: threading.Thread | None = None
        self.config: SystemConfig | None = None
        self.engine = YoloEngine()
        self.video_source = VideoSource()
        self.hardware = HardwareCollector()
        self.telemetry_queue: queue.Queue = queue.Queue(maxsize=32)
        self.frame_queue: queue.Queue = queue.Queue(maxsize=32)
        self._last_frame_time = 0.0
        self._frame_h = 0
        self._frame_w = 0

    def start(self, config: SystemConfig):
        if self._running:
            return
        self.config = config
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    def reconfigure(self, config: SystemConfig):
        old_model = self.config.selectedModel if self.config else ""
        old_rtsp = ""  # 暂时不处理 RTSP 切换，由 LiveDetectTab 管理
        self.config = config

        if config.selectedModel != old_model and config.selectedModel:
            if getattr(config, "localInference", False):
                model_path = os.path.join(_MODEL_DIR, f"{config.selectedModel}.pt")
                try:
                    self.engine.load(model_path)
                except Exception as e:
                    print(f"[Pipeline] 切换模型失败: {e}")
            # 板端模式下不加载本地模型

    def _loop(self):
        try:
            asyncio.run(self._async_loop())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._async_loop())

    async def _async_loop(self):
        print("[Pipeline] PCB 缺陷检测管线启动")

        # 仅当显式开启本地推理且有模型时才加载 .pt；板端场景应保持 localInference=False
        if self.config and self.config.selectedModel and getattr(self.config, "localInference", False):
            model_path = os.path.join(_MODEL_DIR, f"{self.config.selectedModel}.pt")
            try:
                self.engine.load(model_path)
                print(f"[Pipeline] 模型加载成功: {self.config.selectedModel}")
            except Exception as e:
                print(f"[Pipeline] 加载模型失败: {e}")
        else:
            print("[Pipeline] localInference=False，板端模式：本地不跑 YOLO，仅转发板端数据")

        while self._running:
            loop_start = time.time()

            frame = self.video_source.read()
            if frame is None:
                await asyncio.sleep(0.02)
                continue

            self._frame_h, self._frame_w = frame.shape[:2]

            # YOLO track（仅本地推理开启时执行）
            infer_start = time.time()
            tracked: list = []
            if getattr(self.config, "localInference", False) and self.engine.loaded and self.config:
                try:
                    tracked = self.engine.track(
                        frame,
                        conf_threshold=self.config.detectionConfidence,
                        iou_threshold=self.config.iouThreshold,
                    )
                except Exception as e:
                    print(f"[Pipeline] track 失败: {e}")
            infer_elapsed = (time.time() - infer_start) * 1000.0
            self.hardware.record_inference(infer_elapsed)

            # 构建推送数据（仅含 PCB 缺陷字段）
            targets_data = []
            for t in tracked:
                targets_data.append({
                    "id": int(t.id),
                    "type": "defect",
                    "className": _CLASS_NAMES.get(t.class_id, f"class_{t.class_id}"),
                    "x": round(t.x, 2),
                    "y": round(t.y, 2),
                    "width": float(round(t.w, 2)),
                    "height": float(round(t.h, 2)),
                    "confidence": float(round(t.confidence, 3)),
                })

            telemetry = self.hardware.collect()
            self.hardware.record_frame()

            try:
                self.telemetry_queue.put_nowait({
                    "telemetry": telemetry.model_dump(),
                    "targets": targets_data,
                })
            except queue.Full:
                pass

            # 视频帧推送（仅当有标注帧时）
            now = time.time()
            if now - self._last_frame_time >= 0.2:
                annotated = self.engine.plot(frame)
                if annotated is not None:
                    _, jpeg_bytes = cv2.imencode(".jpg", annotated, [
                        cv2.IMWRITE_JPEG_QUALITY, 75,
                    ])
                    try:
                        self.frame_queue.put_nowait(jpeg_bytes.tobytes())
                    except queue.Full:
                        pass
                self._last_frame_time = now

            elapsed = (time.time() - loop_start) * 1000.0
            sleep_time = max(0, 0.05 - elapsed / 1000.0)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
