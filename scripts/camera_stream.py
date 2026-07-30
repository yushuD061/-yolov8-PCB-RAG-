#!/usr/bin/env python3
"""RV1126B 板端：摄像头 + NPU 推理 + WebSocket 推流到 PC"""
import cv2  # 必须在 numpy 之前，兼容 numpy 2.x
import time, json, asyncio, numpy as np, websockets
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from rknnlite.api import RKNNLite

from board_config import BoardConfig, Target, LABELS, load_board_config

# ═══════════════════ 数据结构 ═══════════════════
# 见 board_config.py：BoardConfig / Detection / Target / LABELS

# ═══════════════════ 配置 ═══════════════════
_cfg: BoardConfig = load_board_config()
MODEL_PATH = _cfg.model_path
IMG_SIZE   = _cfg.img_size
CONF       = _cfg.conf
IOU        = _cfg.iou
WS_URL     = _cfg.ws_url
CAMERA     = _cfg.camera

# ═══════════════════ 加载 NPU 模型 ═══════════════════
rknn = RKNNLite()
assert rknn.load_rknn(MODEL_PATH) == 0, "模型加载失败"
assert rknn.init_runtime() == 0, "NPU 初始化失败"
print(f"[RKNN] {MODEL_PATH} 加载完成")

# ═══════════════════ 打开摄像头 ═══════════════════
cap = cv2.VideoCapture(CAMERA)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

def softmax(x, axis=-1):
    e = np.exp(x - np.max(x, axis=axis, keepdims=True))
    return e / np.sum(e, axis=axis, keepdims=True)

def preprocess(frame):
    img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)  # 摄像头横装，旋转 90°
    # letterbox：保持宽高比，灰边填充到 640×640
    h0, w0 = img.shape[:2]
    scale = min(IMG_SIZE / w0, IMG_SIZE / h0)
    nw, nh = int(w0 * scale), int(h0 * scale)
    resized = cv2.resize(img, (nw, nh))
    letterbox = np.full((IMG_SIZE, IMG_SIZE, 3), 114, dtype=np.uint8)
    letterbox[(IMG_SIZE - nh) // 2:(IMG_SIZE - nh) // 2 + nh,
              (IMG_SIZE - nw) // 2:(IMG_SIZE - nw) // 2 + nw] = resized
    img = letterbox.astype(np.float32) / 255.0
    return np.ascontiguousarray(np.expand_dims(img, axis=0), dtype=np.float32)

def preprocess_for_display(frame):
    """仅旋转，用于前端显示"""
    return cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)

def postprocess(outputs, ow, oh):
    """YOLOv8 DFL 解码 + NMS → 归一化 0-100% 坐标
    对齐官方 rknn_yolov8_cam 的后处理逻辑：
    - cls/score_sum 已内置 sigmoid，无需再算
    - score_sum 是快速过滤门
    - 置信度 = cls argmax
    - undo letterbox
    """
    strides = [8, 16, 32]
    reg_max = 16
    nc = 6

    # letterbox 参数
    scale = min(IMG_SIZE / ow, IMG_SIZE / oh)
    pad_x = (IMG_SIZE - int(ow * scale)) // 2
    pad_y = (IMG_SIZE - int(oh * scale)) // 2

    dfl_weight = np.arange(reg_max, dtype=np.float32)

    all_boxes = []
    all_scores = []
    all_cls_ids = []

    for si, stride in enumerate(strides):
        bbox = outputs[si * 3]          # (1, 64,  h, w)
        cls  = outputs[si * 3 + 1]      # (1,  6,  h, w)
        scr  = outputs[si * 3 + 2]      # (1,  1,  h, w)

        h, w = bbox.shape[2], bbox.shape[3]
        grid_n = h * w

        # ── score_sum 快速过滤门 ──
        scr_flat = scr[0].reshape(grid_n)
        keep_mask = scr_flat > CONF
        if keep_mask.sum() == 0:
            continue
        keep_idx = np.where(keep_mask)[0]

        # ── cls argmax（值已 sigmoid） ──
        cls_flat = cls[0].reshape(nc, grid_n).transpose(1, 0)
        cls_flat = cls_flat[keep_idx]
        max_scores = cls_flat.max(axis=1)
        max_cls = cls_flat.argmax(axis=1)

        valid = max_scores > CONF
        if valid.sum() == 0:
            continue
        max_scores = max_scores[valid]
        max_cls = max_cls[valid]
        keep_idx = keep_idx[valid]

        # ── bbox DFL 解码 ──
        bbox = bbox[0].reshape(4, reg_max, grid_n).transpose(2, 0, 1)
        bbox = bbox[keep_idx]
        bbox = softmax(bbox, axis=-1)
        bbox = (bbox * dfl_weight).sum(axis=-1)

        # ── 网格坐标 + 0.5 偏移 ──
        gy, gx = np.mgrid[0:h, 0:w]
        grid_xy = np.stack([gx.ravel(), gy.ravel()], axis=1).astype(np.float32)
        grid_xy = grid_xy[keep_idx] + 0.5

        # 解码到模型空间
        lt = bbox[:, :2]
        rb = bbox[:, 2:]
        x1y1 = (grid_xy - lt) * stride
        x2y2 = (grid_xy + rb) * stride
        boxes = np.concatenate([x1y1, x2y2], axis=1)

        # ── undo letterbox ──
        boxes[:, 0] = (boxes[:, 0] - pad_x) / scale
        boxes[:, 1] = (boxes[:, 1] - pad_y) / scale
        boxes[:, 2] = (boxes[:, 2] - pad_x) / scale
        boxes[:, 3] = (boxes[:, 3] - pad_y) / scale

        all_boxes.append(boxes)
        all_scores.append(max_scores)
        all_cls_ids.append(max_cls)

    if not all_boxes:
        return []

    boxes = np.concatenate(all_boxes, axis=0)
    scores = np.concatenate(all_scores, axis=0)
    cls_ids = np.concatenate(all_cls_ids, axis=0)

    # ── NMS ──
    keep = nms(boxes, scores, IOU)
    boxes = boxes[keep]
    scores = scores[keep]
    cls_ids = cls_ids[keep]

    # ── 转为 0-100% 归一化坐标（中心点 + 宽高） ──
    targets: list[Target] = []
    for i in range(len(boxes)):
        x1, y1, x2, y2 = boxes[i]
        x_center = float((x1 + x2) / 2 / ow * 100)
        y_center = float((y1 + y2) / 2 / oh * 100)
        bw = float((x2 - x1) / ow * 100)
        bh = float((y2 - y1) / oh * 100)
        cid = int(cls_ids[i])
        targets.append(Target(
            id=0,
            class_name=LABELS[cid] if cid < len(LABELS) else f"class_{cid}",
            x=x_center, y=y_center, width=bw, height=bh,
            confidence=float(scores[i]),
        ))
    return targets

def nms(boxes, scores, iou_thresh):
    """纯 numpy NMS → 返回保留的索引"""
    x1 = boxes[:, 0]; y1 = boxes[:, 1]
    x2 = boxes[:, 2]; y2 = boxes[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0, xx2 - xx1 + 1)
        h = np.maximum(0, yy2 - yy1 + 1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        order = order[1:][iou <= iou_thresh]
    return np.array(keep)

async def main():
    while True:
        try:
            print(f"[WS] 正在连接 {WS_URL} ...")
            async with websockets.connect(WS_URL, ping_interval=20, ping_timeout=10, open_timeout=10) as ws:
                print(f"[Pipeline] 已连接 {WS_URL}")
                fc, tick = 0, time.time()
                frame_ok = 0
                while True:
                    ok, frame = cap.read()
                    if not ok:
                        frame_ok += 1
                        if frame_ok == 1:
                            print("[WARN] 摄像头读不到帧")
                        await asyncio.sleep(0.1)
                        continue
                    frame_ok = 0
                    t0 = time.time()

                    tensor = preprocess(frame)
                    # 原图旋转后的尺寸
                    oh_rot, ow_rot = frame.shape[1], frame.shape[0]
                    try:
                        outputs = rknn.inference(inputs=[tensor])
                    except Exception as e:
                        print(f"[ERR] 推理失败: {e}")
                        continue
                    if outputs is None:
                        continue

                    # 每秒打印一次输出统计（调通后删掉）
                    if fc == 0 or time.time() - tick >= 2.0:
                        for idx in [2, 5, 8]:
                            o = outputs[idx]
                            nz = (o > 0.01).sum()
                            ng = (o > 0.25).sum()
                            print(f"[DBG] score_sum[{idx}] max={o.max():.6f}  >0.01:{nz}  >0.25:{ng}")
                        for idx in [1, 4, 7]:
                            o = outputs[idx]
                            nz = (o > 0.01).sum()
                            ng = (o > 0.25).sum()
                            print(f"[DBG] cls[{idx}] max={o.max():.6f}  >0.01:{nz}  >0.25:{ng}")

                    results = postprocess(outputs, ow_rot, oh_rot)
                    infer_ms = (time.time() - t0) * 1000

                    # 发送检测框（Target 序列化）
                    await ws.send(json.dumps({
                        "type": "targets_stream",
                        "data": [
                            {**t.to_dict(), "id": i + 1}
                            for i, t in enumerate(results)
                        ]
                    }))

                    # 发送旋转后的 JPEG 帧
                    if fc % 5 == 0:
                        disp = preprocess_for_display(frame)
                        _, jpeg = cv2.imencode('.jpg', disp, [cv2.IMWRITE_JPEG_QUALITY, 30])
                        await ws.send(jpeg.tobytes())

                    fc += 1
                    if time.time() - tick >= 1.0:
                        print(f"[INFO] FPS={fc/(time.time()-tick):.1f} 检出={len(results)} 延迟={infer_ms:.0f}ms")
                        await ws.send(json.dumps({
                            "type": "telemetry_metrics",
                            "data": {"fps": round(fc/(time.time()-tick),1),
                                     "npu":0,"cpu":0,"memUsed":0,"memTotal":0,
                                     "temp":0,"latency":round(infer_ms,1),
                                     "selectedModel":"yolov8_best"}
                        }))
                        fc, tick = 0, time.time()
        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            print(f"[WS] 连接断开: {e}, 5秒后重连...")
            await asyncio.sleep(5)
        except Exception as e:
            print(f"[ERR] 未知错误: {e}, 5秒后重试...")
            await asyncio.sleep(5)

asyncio.run(main())
