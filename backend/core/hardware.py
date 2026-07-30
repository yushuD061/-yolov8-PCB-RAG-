"""
硬件遥测采集 — 使用 psutil 采集 CPU/内存/FPS 等指标。
NPU 利用率和 SoC 温度在 PC 环境返回 0。
"""

import time
from dataclasses import dataclass
import psutil
from models import HardwareTelemetry


# ═══════════════════ 数据结构 ═══════════════════

@dataclass
class HardwareSnapshot:
    """当前帧硬件快照（含 fps 与延迟，便于单测断言）。"""
    fps: float = 0.0
    cpu: float = 0.0
    memory_used_mb: int = 0
    memory_total_mb: int = 0
    temperature: float = 0.0
    inference_latency_ms: float = 0.0
    status: str = "online"

    def to_telemetry(self) -> HardwareTelemetry:
        return HardwareTelemetry(
            fps=self.fps,
            npuUtilization=0.0,
            cpuUtilization=self.cpu,
            memoryUsed=self.memory_used_mb,
            memoryTotal=self.memory_total_mb,
            socTemperature=self.temperature,
            inferenceLatency=self.inference_latency_ms,
            status=self.status,
        )


# ═══════════════════ 采集逻辑 ═══════════════════

class HardwareCollector:
    def __init__(self):
        self._fps_history: list[float] = []
        self._last_inference_time: float = 0.0

    def record_inference(self, elapsed_ms: float):
        """记录推理耗时"""
        self._last_inference_time = elapsed_ms

    def record_frame(self):
        """记录一帧（用于 FPS 计算）"""
        now = time.time()
        self._fps_history.append(now)
        cutoff = now - 1.0
        self._fps_history = [t for t in self._fps_history if t > cutoff]

    def snapshot(self) -> HardwareSnapshot:
        """采集当前硬件快照"""
        mem = psutil.virtual_memory()
        return HardwareSnapshot(
            fps=float(len(self._fps_history)),
            cpu=psutil.cpu_percent(interval=None),
            memory_used_mb=int(mem.used / 1024 / 1024),
            memory_total_mb=int(mem.total / 1024 / 1024),
            temperature=self._get_cpu_temp(),
            inference_latency_ms=self._last_inference_time,
            status="online",
        )

    def collect(self) -> HardwareTelemetry:
        """采集当前硬件状态（= snapshot().to_telemetry()）。"""
        return self.snapshot().to_telemetry()

    @staticmethod
    def _get_cpu_temp() -> float:
        """获取 CPU 温度（PC 环境可能不支持）"""
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for name, entries in temps.items():
                    if entries:
                        return entries[0].current
        return 0.0
