import { SimulatedTarget, TelemetryMetrics } from '../types';

export function normalizeTargets(rawTargets: any[]): SimulatedTarget[] {
  if (!Array.isArray(rawTargets)) return [];

  return rawTargets.map((det: any) => {
    return {
      id: det.id,
      type: 'defect' as const,
      className: det.className || det.class_name || 'unknown',
      x: det.x ?? 0,                          // 0-100% 中心坐标
      y: det.y ?? 0,                          // 0-100% 中心坐标
      width: det.width ?? 0,                  // 0-100% 框宽
      height: det.height ?? 0,                // 0-100% 框高
      confidence: det.confidence ?? 0,
      defectType: det.defectType || det.className || det.class_name || 'unknown',
      color: det.color || '#ff453a',
    };
  });
}

export function normalizeTelemetry(raw: any): TelemetryMetrics {
  return {
    fps: raw.fps ?? 0,
    npu: raw.npu ?? raw.npuUtilization ?? 0,
    cpu: raw.cpu ?? raw.cpuUtilization ?? 0,
    memUsed: raw.memUsed ?? 0,
    memTotal: raw.memTotal ?? 4096,
    temp: raw.temp ?? raw.socTemperature ?? 0,
    latency: raw.latency ?? 0,
    selectedModel: raw.selectedModel || 'pcb_model',
  };
}
