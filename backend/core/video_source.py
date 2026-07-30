"""
视频源管理 — 支持 RTSP 流 / 本地视频 / 本地图片三种源。
断线自动重连（指数退避），内部使用环形缓冲区解耦采集与消费。

注意：signal.signal() 只能在主线程调用。
FFmpeg 的 pthread_frame.c 断言崩溃通过环境变量 OPENCV_FFMPEG_CAPTURE_OPTIONS
强制单线程解码（threads=1）来解决，不在子线程中操作信号。
"""

import time
import os
from dataclasses import dataclass
import cv2
import numpy as np
from utils.ring_buffer import RingBuffer


# ═══════════════════ 数据结构 ═══════════════════

@dataclass
class VideoSourceState:
    """视频源运行状态快照（便于观测/测试断言）。"""
    uri: str = ""
    source_type: str = "rtsp"   # "rtsp" | "video" | "image"
    is_opened: bool = False
    backoff: float = 1.0
    buffer_size: int = 4


# ═══════════════════ 视频源逻辑 ═══════════════════

class VideoSource:
    def __init__(self, buffer_size: int = 4):
        self._cap: cv2.VideoCapture | None = None
        self._source_type: str = "rtsp"   # "rtsp" | "video" | "image"
        self._uri: str = ""
        self._backoff: float = 1.0
        self._buffer = RingBuffer(buffer_size)
        self._image_frame: np.ndarray | None = None  # 图片模式固定帧

    # ── 状态观测 ──

    def state(self) -> VideoSourceState:
        """返回当前状态快照（不可变视图）。"""
        return VideoSourceState(
            uri=self._uri,
            source_type=self._source_type,
            is_opened=self.is_opened,
            backoff=self._backoff,
            buffer_size=len(self._buffer),
        )

    def _create_capture(self, uri: str):
        """
        创建 VideoCapture。
        Windows 上优先使用 MSMF (Microsoft Media Foundation) 后端，
        完全绕开 FFmpeg 的 pthread_frame.c 多线程断言 bug。
        """
        # Windows: 优先 MSMF（无 FFmpeg 线程安全问题）
        # 检查文件是否存在
        if not os.path.isfile(uri):
            print(f"[VideoSource] 文件不存在: {uri}")
            return cv2.VideoCapture()

        for backend in (cv2.CAP_MSMF, cv2.CAP_ANY, cv2.CAP_FFMPEG):
            try:
                cap = cv2.VideoCapture(uri, backend)
                if cap.isOpened():
                    # 试读一帧验证后端能实际解码
                    ret, test_frame = cap.read()
                    if ret and test_frame is not None:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        print(f"[VideoSource] 后端 {backend} 可用，解码成功")
                        return cap
                    else:
                        print(f"[VideoSource] 后端 {backend} isOpened 但无法解码")
                        cap.release()
                else:
                    print(f"[VideoSource] 后端 {backend} 无法打开文件")
            except Exception as e:
                print(f"[VideoSource] 后端 {backend} 异常: {e}")
        # 全部失败：兜底默认
        print(f"[VideoSource] 所有后端失败，使用默认 VideoCapture")

    def open(self, uri: str, source_type: str = "rtsp"):
        """打开视频源"""
        self.close()
        self._uri = uri
        self._source_type = source_type

        if source_type == "image":
            frame = cv2.imread(uri)
            if frame is None:
                raise ValueError(f"无法加载图片: {uri}")
            self._image_frame = frame
            self._buffer.push(frame)
            return

        self._cap = self._create_capture(uri)

        if source_type == "rtsp":
            # RTSP 优化：减少缓冲，使用 TCP 传输
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            for key, val in {"rtsp_transport": "tcp",
                             "buffer_size": "1024000",
                             "max_delay": "0"}.items():
                self._cap.set(cv2.CAP_PROP_OPENCV_FFMPEG_CAPTURE_OPTIONS,
                              f"{key}={val}")
        elif source_type == "video":
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 4)

    def read(self) -> np.ndarray | None:
        """
        读取一帧。返回 BGR 图像，失败时自动重连并返回 None。
        视频文件读到末尾时自动重新打开（循环播放）。
        MSMF 后端不支持 seek，所以用 close+reopen 实现循环。
        """
        if self._source_type == "image":
            return self._image_frame

        if self._cap is None:
            return None

        if not self._cap.isOpened():
            self._reconnect()
            return None

        ret, frame = self._cap.read()
        if not ret:
            # 视频文件读到末尾 → 重新打开实现循环（MSMF 不支持 seek）
            if self._source_type == "video":
                self._cap.release()
                self._cap = self._create_capture(self._uri)
                if self._cap.isOpened():
                    ret, frame = self._cap.read()
                    if ret and frame is not None:
                        self._backoff = 1.0
                        self._buffer.push(frame)
                        return frame
            self._reconnect()
            return None

        self._backoff = 1.0
        self._buffer.push(frame)
        return frame

        self._backoff = 1.0
        self._buffer.push(frame)
        return frame

    def read_latest(self) -> np.ndarray | None:
        """获取缓存中最新的帧（供视频帧推送使用）"""
        return self._buffer.latest()

    def seek(self, time_sec: float):
        """视频跳转（仅文件模式有效）"""
        if self._cap and self._source_type == "video":
            self._cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)

    def close(self):
        if self._cap:
            self._cap.release()
            self._cap = None
        self._image_frame = None
        self._backoff = 1.0

    def reset(self):
        """停止当前源，重置状态"""
        self.close()
        self._buffer.clear()

    @property
    def source_type(self) -> str:
        return self._source_type

    @property
    def is_opened(self) -> bool:
        if self._source_type == "image":
            return self._image_frame is not None
        return self._cap is not None and self._cap.isOpened()

    def _reconnect(self):
        """指数退避重连（仅 RTSP 且有地址时）"""
        if self._source_type != "rtsp" or not self._uri:
            return
        time.sleep(self._backoff)
        self._backoff = min(self._backoff * 2, 30)
        if self._cap:
            self._cap.release()
        self._cap = self._create_capture(self._uri)
        if self._cap.isOpened():
            self._backoff = 1.0
