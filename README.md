# -yolov8-PCB-RAG-
面向 PCB 生产质检场景，将 YOLOv8 缺陷检测模型部署至 RV1126B 边缘设备，利用板载 NPU完成六类 PCB 缺陷的实时识别；板端通过 WebSocket上传检测框、视频帧和运行指标，PC 端负责实时展示、告警存储、质量统计及RAG领域知识问答。
