"""
应用全局状态 — 所有单例与目录路径集中声明，供 main.py 与 routes/ 复用。
"""

import os

from config import ConfigManager
from core.pipeline import Pipeline, _CLASS_NAMES
from core.hls_streamer import get_hls_streamer
from agent.rag import get_rag_engine
from store.alarm_store import AlarmStore
from store.history_store import HistoryStore
from store.inspection_store import InspectionStore


# ═══════════════════ 单例 ═══════════════════

config_mgr = ConfigManager()
pipeline = Pipeline()
alarm_store = AlarmStore()
history_store = HistoryStore()
inspection_store = InspectionStore()


# ═══════════════════ 目录路径 ═══════════════════

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_BASE_DIR, ".."))

UPLOAD_DIR = os.path.join(_BASE_DIR, "data", "uploads")
HLS_DIR = os.path.join(_BASE_DIR, "data", "hls")
MODEL_DIR = os.path.join(_PROJECT_ROOT, "model")
DETECTION_RESULTS_DIR = os.path.join(_BASE_DIR, "data", "detection_results")


def get_model_path(model_name: str) -> str:
    """根据模型名返回 .pt 路径。"""
    return os.path.join(MODEL_DIR, f"{model_name}.pt")


__all__ = [
    "config_mgr", "pipeline", "alarm_store", "history_store", "inspection_store",
    "UPLOAD_DIR",
    "HLS_DIR", "MODEL_DIR", "DETECTION_RESULTS_DIR",
    "get_model_path",
    "_CLASS_NAMES",
]
