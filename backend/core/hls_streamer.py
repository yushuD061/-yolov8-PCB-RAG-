"""
HLS 推流模块 — 管理 ffmpeg 子进程将 RTSP 流转为 HLS (.m3u8 + .ts)。

用法:
    streamer = HlsStreamer(output_dir="data/hls")
    streamer.start("rtsp://192.168.50.119:8554/live")
    ...
    streamer.stop()
"""

import os
import subprocess
import threading
import time
import shutil
import glob as glob_mod


class HlsStreamer:
    """管理 ffmpeg RTSP → HLS 转换子进程。"""

    def __init__(self, output_dir: str = "data/hls"):
        self._output_dir = os.path.abspath(output_dir)
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._rtsp_url: str = ""
        self._running = False
        self._error: str | None = None
        self._started_at: float = 0.0

    @property
    def is_running(self) -> bool:
        with self._lock:
            if self._process is None:
                return False
            # poll() 返回 None 表示进程仍在运行
            return self._process.poll() is None

    @property
    def status(self) -> dict:
        with self._lock:
            return {
                "running": self.is_running,
                "rtspUrl": self._rtsp_url,
                "startedAt": self._started_at if self._started_at else None,
                "error": self._error,
                "outputDir": self._output_dir,
                "playlistUrl": "/hls/stream.m3u8" if self.is_running else None,
            }

    def start(self, rtsp_url: str, segment_time: int = 1, list_size: int = 4):
        """
        启动 ffmpeg RTSP → HLS 转换。

        Args:
            rtsp_url: 板端 RTSP 地址 (如 rtsp://192.168.50.119:8554/live)
            segment_time: 每个 .ts 分片时长（秒，默认 1）
            list_size: m3u8 播放列表保留分片数（默认 4）
        """
        with self._lock:
            # 先停掉旧进程
            self._stop_unsafe()

            self._error = None
            self._rtsp_url = rtsp_url

            # 确保输出目录存在且干净
            os.makedirs(self._output_dir, exist_ok=True)
            self._clean_dir_unsafe()

            playlist_path = os.path.join(self._output_dir, "stream.m3u8")
            segments_pattern = os.path.join(self._output_dir, "segment_%03d.ts")

            # ffmpeg 命令：RTSP → HLS（copy 视频编码，不重新编码）
            cmd = [
                "ffmpeg",
                "-rtsp_transport", "tcp",           # TCP 传输更稳定
                "-i", rtsp_url,
                "-c:v", "copy",                      # 不重新编码（节省 CPU）
                "-an",                                # 暂时去掉音频
                "-f", "hls",
                "-hls_time", str(segment_time),
                "-hls_list_size", str(list_size),
                "-hls_flags", "delete_segments+program_date_time",
                "-hls_segment_filename", segments_pattern,
                "-loglevel", "warning",              # 只输出警告
                playlist_path,
            ]

            try:
                self._process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                self._started_at = time.time()
                self._running = True

                # 启动错误监控线程
                t = threading.Thread(target=self._monitor_stderr, daemon=True)
                t.start()
            except FileNotFoundError:
                self._error = "ffmpeg 未安装或不在 PATH 中"
                self._process = None
                self._running = False
            except Exception as e:
                self._error = str(e)
                self._process = None
                self._running = False

    def stop(self):
        """停止 ffmpeg 进程并清理 HLS 文件。"""
        with self._lock:
            self._stop_unsafe()

    def _stop_unsafe(self):
        """不加锁的内部停止方法。"""
        self._running = False
        proc = self._process
        self._process = None

        if proc is not None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

        self._clean_dir_unsafe()
        self._rtsp_url = ""
        self._started_at = 0.0

    def _clean_dir_unsafe(self):
        """清空 HLS 输出目录。"""
        try:
            if os.path.isdir(self._output_dir):
                for f in glob_mod.glob(os.path.join(self._output_dir, "*")):
                    try:
                        os.remove(f)
                    except OSError:
                        pass
        except Exception:
            pass

    def _monitor_stderr(self):
        """读取 ffmpeg stderr 以捕获错误。"""
        proc = self._process
        if proc is None:
            return
        try:
            for line in proc.stderr:
                line = line.strip()
                if line:
                    # 只记录有意义的信息
                    if any(kw in line.lower() for kw in ("error", "fail", "cannot", "invalid", "connection refused", "404", "timed out")):
                        with self._lock:
                            self._error = line[:200]
            # stderr 关闭 → 进程已结束
            if proc.poll() is not None and proc.returncode != 0:
                with self._lock:
                    if self._error is None:
                        self._error = f"ffmpeg 异常退出 (code={proc.returncode})"
                    self._running = False
        except Exception:
            pass


# 全局单例
_hls_streamer: HlsStreamer | None = None


def get_hls_streamer(output_dir: str = "data/hls") -> HlsStreamer:
    """获取全局 HlsStreamer 单例。"""
    global _hls_streamer
    if _hls_streamer is None:
        abs_dir = os.path.join(os.path.dirname(__file__), "..", output_dir)
        _hls_streamer = HlsStreamer(output_dir=abs_dir)
    return _hls_streamer
