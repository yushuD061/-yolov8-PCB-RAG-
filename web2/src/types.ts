export type TabId = 'live_detect' | 'image_rec' | 'history' | 'config' | 'user' | 'rag';
export type TargetType = 'defect';

// 6 类 PCB 缺陷中英文映射
export const DEFECT_NAMES_CN: Record<string, string> = {
  missing_hole: '漏孔',
  mouse_bite: '鼠咬',
  open_circuit: '开路',
  short: '短路',
  spur: '毛刺',
  spurious_copper: '残铜',
};

export function getDefectNameCn(className: string): string {
  return DEFECT_NAMES_CN[className] || className || '未知';
}

export interface SimulatedTarget {
  id: number;
  type: TargetType;
  className: string;          // 缺陷英文名（如 "missing_hole"）
  x: number;                  // 框中心 X（像素，1100×620 基准）
  y: number;                  // 框中心 Y
  width: number;              // 框宽
  height: number;             // 框高
  confidence: number;         // 置信度 0-1
  defectType: string;         // 缺陷类型（同 className）
  color: string;
}

export interface TelemetryMetrics {
  fps: number;
  npu: number;        // Percentage
  cpu: number;        // Percentage
  memUsed: number;    // MB used
  memTotal: number;   // MB total
  temp: number;       // Celsius Temperature
  latency: number;    // Latency in ms
  selectedModel: string;
}

export interface AlarmEvent {
  id: string;
  timestamp: string;
  type: string;
  targetId: number;
  description: string;
  source: 'live' | 'image';  // 检测模式：实时检测 / 图片检测
  batchId?: string;          // 同一次批量检测共享的批次编号
  itemName?: string;         // 被检测图片或 PCB 标识
  isGood?: boolean;          // true 表示本次检测未发现缺陷
  className?: string;        // 缺陷类别英文名，用于稳定解析模型 class_id
}

export interface SystemConfig {
  selectedModel: string;          // 推理模型
  localInference: boolean;        // PC 端是否本地跑 YOLO（板端场景应关闭）
  // 检测存储
  saveResults: boolean;           // 自动保存检测结果
  retentionDays: number;          // 结果保留天数
  jpegQuality: number;           // 保存图片质量 50-100
  // 板端配置
  maxFps: number;                // 最大推理帧率 15-60
  npuMode: 'powersave' | 'balanced' | 'performance';  // NPU 频率模式
  tempWarning: number;           // 温度告警阈值 °C
  // 告警与通知
  reviewThreshold: number;       // 复查置信度阈值（低于此值的缺陷标记复查）
  consecutiveAlerts: number;     // 连续缺陷告警数
}

// ═══════════════════ RAG ═══════════════════

export interface RagDocument {
  id: string;
  name: string;
  size: number;
  uploadedAt: string;
  status: 'indexing' | 'ready' | 'error';
  chunks: number;
}

export interface RagMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface RagSource {
  doc_name: string;
  content: string;
  score: number;
  source?: string;
}

export interface RagQueryResult {
  answer: string;
  sources: RagSource[];
}

export interface LlmApiConfig {
  endpoint: string;
  apiKey: string;
  model: string;
}

export const DEFAULT_LLM_CONFIG: LlmApiConfig = {
  endpoint: 'https://api.siliconflow.cn/v1/chat/completions',
  apiKey: '',
  model: 'Qwen/Qwen2.5-7B-Instruct',
};

// ═══════════════════ WebSocket 协议（discriminated union）═══════════════════

export interface WSStatusChange { type: 'status_change'; data: { connected: boolean } }
export interface WSTargetsStream { type: 'targets_stream'; data: SimulatedTarget[] }
export interface WSTelemetryMetrics { type: 'telemetry_metrics'; data: TelemetryMetrics }
export interface WSLogBroadcast { type: 'log_broadcast'; data: { message: string } }
export interface WSResult { type: 'result'; id: string; channel: string; data: any }
export interface WSError { type: 'error'; id: string; channel: string; data: { message: string } }

export type WSPushMessage =
  | WSStatusChange
  | WSTargetsStream
  | WSTelemetryMetrics
  | WSLogBroadcast
  | WSResult
  | WSError;

export interface WSRequest {
  id: string;
  method: string;
  channel: string;
  data?: Record<string, unknown>;
}
