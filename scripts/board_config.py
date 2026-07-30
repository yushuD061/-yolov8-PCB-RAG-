"""
板端公共配置 — RV1126B 板端脚本共用。
统一在此声明数据类型结构（dataclass + 常量），各脚本仅负责业务逻辑。
"""

import os
from dataclasses import dataclass, field


# ═══════════════════ 缺陷类别常量 ═══════════════════

LABELS: list[str] = [
    "missing_hole",
    "mouse_bite",
    "open_circuit",
    "short",
    "spur",
    "spurious_copper",
]


# ═══════════════════ 数据结构 ═══════════════════

@dataclass
class BoardConfig:
    """板端运行参数（可被环境变量覆盖）。"""
    model_path: str = "model/yolov8_best.rknn"
    camera: str = "/dev/video-camera0"
    img_size: int = 640
    conf: float = 0.25
    iou: float = 0.45
    # PC 后端 WebSocket 地址
    ws_url: str = "ws://192.168.50.74:5000/ws"


@dataclass
class Detection:
    """板端 YOLO 后处理输出：像素坐标框 + 类别 + 置信度。"""
    class_name: str
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


@dataclass
class Target:
    """已归一化（0-100%）的 WS 推送目标，对齐前端 SimulatedTarget。"""
    id: int
    type: str = "defect"
    class_name: str = ""
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "className": self.class_name,
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "width": round(self.width, 2),
            "height": round(self.height, 2),
            "confidence": round(self.confidence, 3),
        }


def load_board_config(defaults: BoardConfig | None = None) -> BoardConfig:
    """从环境变量加载配置，未设置则使用 defaults。"""
    cfg = defaults or BoardConfig()
    cfg.model_path = os.environ.get("BOARD_MODEL_PATH", cfg.model_path)
    cfg.camera = os.environ.get("BOARD_CAMERA", cfg.camera)
    cfg.img_size = int(os.environ.get("BOARD_IMG_SIZE", str(cfg.img_size)))
    cfg.conf = float(os.environ.get("BOARD_CONF", str(cfg.conf)))
    cfg.iou = float(os.environ.get("BOARD_IOU", str(cfg.iou)))
    cfg.ws_url = os.environ.get("BOARD_WS_URL", cfg.ws_url)
    return cfg