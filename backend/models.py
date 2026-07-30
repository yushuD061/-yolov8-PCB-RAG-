"""
Pydantic 数据模型 — 对齐前端 types.ts 的 TypeScript 接口。
PCB 缺陷检测场景：6 类缺陷，无交通相关字段。
"""

from pydantic import BaseModel
from typing import Optional


class SystemConfig(BaseModel):
    """全局系统配置"""
    detectionConfidence: float = 0.45      # 默认检测置信度
    iouThreshold: float = 0.50             # 默认 IoU 阈值
    selectedModel: str = "pcb_model"       # 模型文件名（不含扩展名）
    saveResults: bool = True               # 自动保存检测结果
    retentionDays: int = 30                # 结果保留天数
    jpegQuality: int = 85                 # 保存图片质量 50-100
    maxFps: int = 30                      # 最大推理帧率 15-60
    npuMode: str = "balanced"             # NPU 频率模式: powersave/balanced/performance
    tempWarning: int = 75                 # 温度告警阈值 °C
    reviewThreshold: float = 0.35         # 复查置信度阈值
    consecutiveAlerts: int = 5            # 连续缺陷告警数
    localInference: bool = False              # PC 端本地是否跑 YOLO 推理（板端场景应关闭）
    enableInferenceTelemetry: bool = False


class HardwareTelemetry(BaseModel):
    """硬件遥测"""
    fps: float
    npuUtilization: float
    cpuUtilization: float
    memoryUsed: int
    memoryTotal: int
    socTemperature: float
    inferenceLatency: float
    status: str = "online"


class DetectionTarget(BaseModel):
    """检测目标（PCB 缺陷）"""
    id: int
    type: str = "defect"                  # 固定为 "defect"
    className: str                        # 缺陷英文名（如 "missing_hole"）
    confidence: float = 0.0               # 置信度 0-1
    x: float                              # 框中心 X（0-100%）
    y: float                              # 框中心 Y（0-100%）
    width: float                          # 框宽（0-100%）
    height: float                         # 框高（0-100%）


class AlarmRecord(BaseModel):
    """检测告警记录"""
    id: str
    timestamp: str                        # ISO 8601
    targetId: int
    type: str
    message: str
