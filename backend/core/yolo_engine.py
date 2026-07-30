"""
Ultralytics YOLO 引擎 — 基于 model.track() 实现检测+追踪一体化。
替代旧的 ONNXEngine + ByteTrack 组合。
用法与用户提供的脚本一致：
    model = YOLO("yolo26n.pt")
    results = model.track(frame, persist=True)
    annotated_frame = results[0].plot()
"""

import os
import numpy as np
import cv2


class TrackedObject:
    """追踪目标数据，仅含 PCB 缺陷所需字段"""
    def __init__(self, track_id: int, x: float, y: float, w: float, h: float,
                 class_id: int, confidence: float):
        self.id = track_id
        self.x = x                          # 框中心 X（0-100%）
        self.y = y                          # 框中心 Y（0-100%）
        self.w = w                          # 框宽（0-100%）
        self.h = h                          # 框高（0-100%）
        self.class_id = class_id
        self.confidence = confidence


class YoloEngine:
    """封装 Ultralytics YOLO，提供 track() 接口"""

    def __init__(self):
        self._model = None
        self._model_path: str | None = None
        self._names: dict[int, str] = {}  # class_id → name
        self.loaded = False

    def load(self, model_path: str):
        """加载 .pt 模型"""
        if self._model_path == model_path and self._model:
            return
        self.unload()
        self._model = YOLO(model_path)
        self._model_path = model_path
        self._names = self._model.names if hasattr(self._model, 'names') else {}
        self.loaded = True

    def unload(self):
        self._model = None
        self._model_path = None
        self._names = {}
        self.loaded = False

    def track(self, frame: np.ndarray,
              conf_threshold: float = 0.25,
              iou_threshold: float = 0.45,
              classes: list[int] | None = None) -> list[TrackedObject]:
        """
        对一帧执行检测+追踪，返回 TrackedObject 列表。
        坐标转换为 0-100% 相对值，与前端 dataAdapter.ts 兼容。
        """
        if self._model is None:
            return []

        h_orig, w_orig = frame.shape[:2]

        # 调用 Ultralytics model.track() — 与用户提供的脚本一致
        results = self._model.track(
            frame,
            persist=True,
            conf=conf_threshold,
            iou=iou_threshold,
            classes=classes,
            verbose=False,
        )

        if not results or len(results) == 0:
            return []

        boxes = results[0].boxes
        if boxes is None or boxes.id is None:
            return []

        tracked = []
        xywh = boxes.xywh.cpu().numpy()       # [N, 4] pixel coords
        ids = boxes.id.int().cpu().numpy()     # [N] track IDs
        cls_ids = boxes.cls.int().cpu().numpy() if boxes.cls is not None else np.zeros_like(ids)
        confs = boxes.conf.cpu().numpy() if boxes.conf is not None else np.ones_like(ids, dtype=float)

        for i in range(len(ids)):
            cx_px, cy_px, w_px, h_px = xywh[i]
            class_id = int(cls_ids[i])

            # 像素 → 0-100% 相对坐标（与旧 ONNXEngine 输出格式一致）
            cx = (cx_px / w_orig) * 100.0
            cy = (cy_px / h_orig) * 100.0
            bw = (w_px / w_orig) * 100.0
            bh = (h_px / h_orig) * 100.0

            obj = TrackedObject(
                track_id=int(ids[i]),
                x=round(cx, 2),
                y=round(cy, 2),
                w=round(bw, 2),
                h=round(bh, 2),
                class_id=class_id,
                confidence=float(confs[i]),
            )
            # 保留历史路径（由 pipeline 管理）
            tracked.append(obj)

        return tracked

    def plot(self, frame: np.ndarray) -> np.ndarray | None:
        """返回最后一次 track() 的标注帧（框+标签已绘制），无结果时返回 None"""
        if self._model is None:
            return None
        # 最近一次推理结果缓存在 model.predictor 中
        if hasattr(self._model, 'predictor') and self._model.predictor.results:
            return self._model.predictor.results[0].plot()
        return None

    @property
    def class_names(self) -> dict[int, str]:
        return self._names


# 延迟导入，避免模块加载时依赖 ultralytics
from ultralytics import YOLO  # noqa: E402
