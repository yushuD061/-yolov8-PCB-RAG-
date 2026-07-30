"""
透视校正工具 — 像素坐标 ↔ 世界坐标变换。
"""

import numpy as np


class PerspectiveTransform:
    """基于源四边形到目标四边形的单应性变换"""

    def __init__(self):
        self._matrix: np.ndarray | None = None
        self._inverse: np.ndarray | None = None

    def calibrate(self, src_points: list[tuple[float, float]],
                  dst_points: list[tuple[float, float]]):
        """
        标定透视变换矩阵。
        src_points: 原始图像中的 4 个点 [左上, 右上, 左下, 右下]
        dst_points: 目标鸟瞰图中的 4 个对应点
        """
        src = np.array(src_points, dtype=np.float32)
        dst = np.array(dst_points, dtype=np.float32)
        self._matrix = cv2.getPerspectiveTransform(src, dst)
        self._inverse = cv2.getPerspectiveTransform(dst, src)

    def warp(self, frame: np.ndarray, width: int = 400, height: int = 400
             ) -> np.ndarray:
        """将透视变换后的鸟瞰图"""
        if self._matrix is None:
            return frame
        return cv2.warpPerspective(frame, self._matrix, (width, height))

    def pixel_to_world(self, x: float, y: float) -> tuple[float, float]:
        """像素坐标 → 世界坐标"""
        if self._inverse is None:
            return (x, y)
        pt = np.array([[[x, y]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt, self._inverse)
        return (transformed[0, 0, 0], transformed[0, 0, 1])

    def world_to_pixel(self, wx: float, wy: float) -> tuple[float, float]:
        """世界坐标 → 像素坐标"""
        if self._matrix is None:
            return (wx, wy)
        pt = np.array([[[wx, wy]]], dtype=np.float32)
        transformed = cv2.perspectiveTransform(pt, self._matrix)
        return (transformed[0, 0, 0], transformed[0, 0, 1])


import cv2  # noqa: E402
