"""
配置管理：从 data/config.json 加载/保存 SystemConfig。
支持部分更新和监听器模式（配置变更通知 pipeline 热生效）。
"""

import json
import os
from typing import Callable
from models import SystemConfig

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "data", "config.json")

_DEFAULT_CONFIG = SystemConfig()


class ConfigManager:
    def __init__(self):
        self._config: SystemConfig = _DEFAULT_CONFIG.model_copy()
        self._listeners: list[Callable[[SystemConfig], None]] = []

    def load(self) -> SystemConfig:
        """从 JSON 文件加载配置，文件不存在时使用默认值"""
        if os.path.exists(_CONFIG_PATH):
            try:
                with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 只取 SystemConfig 中有的字段，忽略旧字段
                valid_keys = SystemConfig.model_fields.keys()
                filtered = {k: v for k, v in data.items() if k in valid_keys}
                self._config = SystemConfig(**filtered)
            except (json.JSONDecodeError, TypeError):
                pass
        return self._config

    def get(self) -> SystemConfig:
        return self._config

    def update(self, partial: dict) -> SystemConfig:
        """部分更新配置，合并到当前配置后持久化并通知监听器"""
        merged = self._config.model_dump()
        merged.update(partial)
        self._config = SystemConfig(**merged)
        self._save()
        for listener in self._listeners:
            listener(self._config)
        return self._config

    def on_change(self, callback: Callable[[SystemConfig], None]):
        """注册配置变更监听器"""
        self._listeners.append(callback)

    def _save(self):
        os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._config.model_dump(), f, indent=2, ensure_ascii=False)
