import React, { useRef, useState, useEffect } from 'react';
import { Settings, VideoOff, Cpu, Thermometer, Zap, Wifi } from 'lucide-react';
import { SimulatedTarget, getDefectNameCn } from '../types';

interface LiveDetectTabProps {
  targets: SimulatedTarget[];
  selectedTargetId: number | null;
  setSelectedTargetId: (id: number | null) => void;
  pushLog: (msg: string) => void;
  videoFrameUrl: string | null;
  wsConnected: boolean;
  metrics: { fps: number; npu: number; temp: number };
}

// 6 类 PCB 缺陷颜色映射
const DEFECT_COLORS: Record<string, string> = {
  missing_hole: '#ff453a',     // 漏孔 — 红
  mouse_bite: '#ff9f0a',       // 鼠咬 — 橙
  open_circuit: '#bf5af2',     // 开路 — 紫
  short: '#0a84ff',            // 短路 — 蓝
  spur: '#30d158',             // 毛刺 — 绿
  spurious_copper: '#ffd60a',  // 残铜 — 黄
};

export const LiveDetectTab: React.FC<LiveDetectTabProps> = ({
  targets,
  selectedTargetId,
  setSelectedTargetId,
  pushLog,
  videoFrameUrl,
  wsConnected,
  metrics,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  const boardFps = metrics.fps;
  const npuUtil = metrics.npu;
  const boardTemp = metrics.temp;

  // 检测参数
  const [confidence, setConfidence] = useState<number>(0.45);
  const [iouThreshold, setIouThreshold] = useState<number>(0.50);

  // 缺陷统计
  const [defectCounts, setDefectCounts] = useState<Record<string, number>>({});

  // 实时更新缺陷统计
  useEffect(() => {
    const counts: Record<string, number> = {};
    targets.forEach((t) => {
      const name = t.className || 'unknown';
      counts[name] = (counts[name] || 0) + 1;
    });
    setDefectCounts(counts);
  }, [targets]);

  const getDefectColor = (className: string): string => {
    return DEFECT_COLORS[className] || '#0a84ff';
  };

  const selectedTarget = targets.find((t) => t.id === selectedTargetId);

  return (
    <div className="flex-1 p-6 overflow-y-auto grid grid-cols-12 gap-6 transition-colors duration-250">
      {/* 视频流区域 */}
      <div className="col-span-12 lg:col-span-9 flex flex-col space-y-4">
        <div
          ref={containerRef}
          className="relative aspect-[1100/620] bg-[#09090b] rounded-xl overflow-hidden border border-[#2c2c2e] flex items-center justify-center select-none shadow-2xl"
        >
          {wsConnected ? (
            <>
              {/* WebSocket 视频帧（板端 kmsgrab 截屏 → MJPEG） */}
              {videoFrameUrl && (
                <img
                  src={videoFrameUrl}
                  alt="Live frame"
                  className="absolute inset-0 w-full h-full object-contain bg-black"
                />
              )}

              {/* 无视频帧时的占位背景 */}
              {!videoFrameUrl && (
                <div className="absolute inset-0 bg-gradient-to-b from-[#0e0e11] to-[#121217] flex items-center justify-center">
                  <div className="absolute inset-0 opacity-[0.03] pointer-events-none bg-[radial-gradient(#0a84ff_1px,transparent_1px)] [background-size:20px_20px]" />
                </div>
              )}

              {/* 等待视频帧时的提示 */}
              {!videoFrameUrl && (
                <div className="absolute inset-0 flex items-center justify-center">
                  <div className="text-center text-[#8e8e93]">
                    <Zap className="h-16 w-16 text-[#30d158] mx-auto mb-4 animate-pulse" />
                    <p className="text-sm text-white font-semibold">RV1126B 实时推理中</p>
                    <p className="text-xs mt-1">FPS: {boardFps} | NPU: {npuUtil}%</p>
                  </div>
                </div>
              )}

              {/* 画面不显示检测框，仅做纯净视频流展示；检测结果见下方统计 / 目标列表 */}

              {/* 板端状态叠加层 */}
              <div className="absolute top-4 left-4 flex space-x-2 z-10">
                <span className="bg-black/75 backdrop-blur-md px-3 py-1.5 text-white text-[11px] font-semibold rounded-lg border border-white/10 font-sans flex items-center space-x-2">
                  <Cpu className="h-3.5 w-3.5 text-[#0a84ff]" />
                  <span>RV1126B 实时检测</span>
                </span>
              </div>
              <div className="absolute bottom-4 left-4 flex space-x-3 z-10">
                <span className="bg-black/75 px-2.5 py-1 rounded text-[10px] font-mono text-[#30d158] border border-white/5">
                  <Zap className="h-3 w-3 inline mr-1" />{boardFps} FPS
                </span>
                <span className="bg-black/75 px-2.5 py-1 rounded text-[10px] font-mono text-[#bf5af2] border border-white/5">
                  <Cpu className="h-3 w-3 inline mr-1" />NPU {npuUtil}%
                </span>
                <span className="bg-black/75 px-2.5 py-1 rounded text-[10px] font-mono text-[#ff9f0a] border border-white/5">
                  <Thermometer className="h-3 w-3 inline mr-1" />{boardTemp}°C
                </span>
              </div>
            </>
          ) : (
            <div className="absolute inset-0 bg-[#0c0c0e] flex flex-col items-center justify-center text-[#8e8e93] p-6 text-center">
              <div className="h-16 w-16 rounded-full bg-[#ff453a]/10 border border-[#ff453a]/25 flex items-center justify-center text-[#ff3b30] mb-4 animate-pulse">
                <VideoOff className="h-7 w-7 stroke-[1.5]" />
              </div>
              <p className="text-sm font-semibold text-[#f5f5f7] tracking-wide">RV1126B 板端未连接</p>
              <p className="text-xs text-[#8e8e93] mt-2 max-w-sm leading-relaxed">
                WebSocket 已断开，请确认板端 camera_stream.py 正在运行。
              </p>
            </div>
          )}

          <div className="absolute top-4 right-4 z-20">
            {wsConnected && (
              <span className="inline-flex items-center space-x-1.5 bg-[#30d158]/10 border border-[#30d158]/30 px-3 py-1 text-[#30d158] text-[10px] font-mono font-bold rounded-full shadow-[0_0_12px_rgba(48,209,88,0.15)] select-none">
                <span className="h-2 w-2 rounded-full bg-[#30d158] animate-pulse" />
                <span>RV1126B 已连接</span>
              </span>
            )}
          </div>
        </div>

        {/* 连接控制栏 */}
        <div className="bg-[#1c1c1e] p-4 rounded-xl border border-[#2c2c2e] flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="flex items-center gap-3 text-xs text-[#8e8e93]">
              <span>WS 状态: <span className={wsConnected ? 'text-[#30d158]' : 'text-[#ff453a]'}>{wsConnected ? '已连接' : '未连接'}</span></span>
            </div>
          </div>

          {wsConnected && (
            <div className="flex items-center space-x-4 text-xs">
              <span className="text-[#8e8e93]">目标数: <span className="text-white font-bold">{targets.length}</span></span>
              <span className="text-[#8e8e93]">FPS: <span className="text-[#30d158] font-bold">{boardFps}</span></span>
            </div>
          )}
        </div>

        {/* 实时缺陷统计 */}
        {wsConnected && targets.length > 0 && (
          <div className="bg-[#1c1c1e] p-3 rounded-xl border border-[#2c2c2e]">
            <div className="text-xs text-[#8e8e93] mb-2">实时缺陷统计</div>
            <div className="flex flex-wrap gap-2">
              {Object.entries(defectCounts).map(([name, count]) => (
                <span key={name} className="inline-flex items-center space-x-1 text-[10px] px-2 py-0.5 rounded-full font-bold"
                  style={{ backgroundColor: (getDefectColor(name)) + '20', color: getDefectColor(name) }}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: getDefectColor(name) }} />
                  <span>{getDefectNameCn(name)}: {count}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 目标列表 */}
        {wsConnected && targets.length > 0 && (
          <div className="bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] overflow-hidden">
            <div className="px-6 py-4 border-b border-[#2c2c2e] flex justify-between items-center select-none">
              <h3 className="text-sm font-semibold text-[#8e8e93] tracking-wide uppercase font-sans">
                实时缺陷队列 ({targets.length})
              </h3>
              <span className="text-xs text-[#8e8e93] font-mono">RV1126B 推理周期: {Math.round(1000 / boardFps)}ms</span>
            </div>
            <div className="max-h-[220px] overflow-y-auto">
              <table className="w-full text-left border-collapse text-xs font-mono">
                <thead className="sticky top-0 bg-[#2c2c2e] text-[#8e8e93] font-bold select-none z-10">
                  <tr>
                    <th className="px-6 py-3">ID</th>
                    <th className="px-6 py-3">缺陷类型</th>
                    <th className="px-6 py-3">置信度</th>
                    <th className="px-6 py-3">位置 X</th>
                    <th className="px-6 py-3">位置 Y</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#2c2c2e]">
                  {targets.map((t) => (
                    <tr
                      key={t.id}
                      onClick={() => setSelectedTargetId(t.id)}
                      className={`hover:bg-white/5 cursor-pointer transition ${selectedTargetId === t.id ? 'bg-[#0a84ff]/10' : ''}`}
                    >
                      <td className="px-6 py-3 font-semibold text-white">#{t.id}</td>
                      <td className="px-6 py-3">
                        <span className="inline-flex items-center space-x-1">
                          <span className="w-2 h-2 rounded-full" style={{ backgroundColor: getDefectColor(t.className) }} />
                          <span style={{ color: getDefectColor(t.className) }}>{getDefectNameCn(t.className)}</span>
                        </span>
                      </td>
                      <td className="px-6 py-3 text-[#30d158]">{(t.confidence * 100).toFixed(1)}%</td>
                      <td className="px-6 py-3 text-white">{Math.round(t.x)}</td>
                      <td className="px-6 py-3 text-white">{Math.round(t.y)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* 缺陷详情 — 始终显示 */}
        <div className="bg-[#1c1c1e] p-4 rounded-xl border border-[#2c2c2e]">
          <h4 className="text-xs font-semibold text-[#8e8e93] uppercase tracking-wide border-b border-[#2c2c2e] pb-2 mb-3">
            缺陷详情
          </h4>
            {selectedTarget ? (
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-xs font-mono">
                <div className="bg-black/30 p-2.5 rounded-lg border border-[#2c2c2e]">
                  <span className="text-[#8e8e93] block text-[10px] mb-1">缺陷类型</span>
                  <span className="font-bold" style={{ color: getDefectColor(selectedTarget.className) }}>
                    {getDefectNameCn(selectedTarget.className)}
                  </span>
                </div>
                <div className="bg-black/30 p-2.5 rounded-lg border border-[#2c2c2e]">
                  <span className="text-[#8e8e93] block text-[10px] mb-1">英文名称</span>
                  <span className="text-white font-semibold">{selectedTarget.className}</span>
                </div>
                <div className="bg-black/30 p-2.5 rounded-lg border border-[#2c2c2e]">
                  <span className="text-[#8e8e93] block text-[10px] mb-1">置信度</span>
                  <span className="text-[#30d158] font-bold">{(selectedTarget.confidence * 100).toFixed(1)}%</span>
                </div>
                <div className="bg-black/30 p-2.5 rounded-lg border border-[#2c2c2e]">
                  <span className="text-[#8e8e93] block text-[10px] mb-1">位置</span>
                  <span className="text-white font-semibold">({Math.round(selectedTarget.x)}, {Math.round(selectedTarget.y)})</span>
                </div>
                <div className="bg-black/30 p-2.5 rounded-lg border border-[#2c2c2e]">
                  <span className="text-[#8e8e93] block text-[10px] mb-1">目标 ID</span>
                  <span className="text-white font-semibold">#{selectedTarget.id}</span>
                </div>
              </div>
            ) : (
              <div className="text-center text-[#8e8e93] text-xs py-4">
                点击下方目标列表查看详情
              </div>
            )}
          </div>
        </div>

      {/* 右侧面板 */}
      <div className="col-span-12 lg:col-span-3 flex flex-col space-y-6 select-none">
        {/* RV1126B 连接状态 */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] space-y-4">
          <div className="flex items-center space-x-2 border-b border-[#2c2c2e] pb-3">
            <Settings className="h-4 w-4 text-[#0a84ff]" />
            <h3 className="text-sm font-semibold text-white">RV1126B 连接状态</h3>
          </div>

          <div className="space-y-4 text-xs font-mono">
            <div className="flex items-center space-x-2">
              <span className={`h-2 w-2 rounded-full ${wsConnected ? 'bg-[#30d158] animate-pulse' : 'bg-[#ff453a]'}`} />
              <span className="text-[#8e8e93]">WebSocket</span>
              <span className={`font-bold ${wsConnected ? 'text-[#30d158]' : 'text-[#ff453a]'}`}>
                {wsConnected ? '已连接' : '未连接'}
              </span>
            </div>
            {wsConnected && (
              <div className="text-[10px] text-[#8e8e93]">
                {'画面通过 WebSocket 直推 (kmsgrab 截屏 → MJPEG)。'}
              </div>
            )}
          </div>
        </div>

        {/* 视频源信息 */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] space-y-4">
          <div className="flex items-center space-x-2 border-b border-[#2c2c2e] pb-3">
            <Wifi className="h-4 w-4 text-[#30d158]" />
            <h3 className="text-sm font-semibold text-white">视频源</h3>
          </div>
          <div className="space-y-3 text-xs font-mono">
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">传输方式</span>
              <span className="text-[#30d158] font-bold">WebSocket 直连</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">板端采集</span>
              <span className="text-white">kmsgrab (DRM 截屏)</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">编码格式</span>
              <span className="text-white">MJPEG</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">画面旋转</span>
              <span className="text-white">右旋 90°</span>
            </div>
            {wsConnected && (
              <div className="text-[10px] text-[#30d158] text-center mt-2">
                板端 KMS 抓屏 → MJPEG → WS → 前端实时显示
              </div>
            )}
          </div>
        </div>

        {/* 板端状态 */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] space-y-4">
          <div className="flex items-center space-x-2 border-b border-[#2c2c2e] pb-3">
            <Cpu className="h-4 w-4 text-[#30d158]" />
            <h3 className="text-sm font-semibold text-white">板端状态</h3>
          </div>
          <div className="space-y-3 text-xs font-mono">
            <div className="flex justify-between items-center">
              <span className="text-[#8e8e93]">连接状态</span>
              <span className={`font-bold ${wsConnected ? 'text-[#30d158]' : 'text-[#ff453a]'}`}>
                {wsConnected ? '已连接' : '未连接'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">芯片型号</span>
              <span className="text-white">RV1126B</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">推理帧率</span>
              <span className="text-[#30d158] font-bold">{boardFps} FPS</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">NPU 占用</span>
              <span className="text-[#bf5af2] font-bold">{npuUtil}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[#8e8e93]">板端温度</span>
              <span className="text-[#ff9f0a] font-bold">{boardTemp}°C</span>
            </div>
          </div>
        </div>

        {/* 检测参数 */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-2 border-b border-[#2c2c2e] pb-3">
            <Settings className="h-4 w-4 text-[#0a84ff]" />
            <h3 className="text-sm font-semibold text-white">检测参数</h3>
          </div>
          <div className="space-y-4 text-xs">
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-[#a2a2a7]">置信阈值</label>
                <span className="text-[#30d158] font-mono font-bold">{confidence.toFixed(2)}</span>
              </div>
              <input type="range" min="0.1" max="0.95" step="0.05" value={confidence}
                onChange={(e) => setConfidence(parseFloat(e.target.value))}
                className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#30d158]" />
            </div>
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-[#a2a2a7]">交并比阈值</label>
                <span className="text-[#bf5af2] font-mono font-bold">{iouThreshold.toFixed(2)}</span>
              </div>
              <input type="range" min="0.1" max="0.9" step="0.05" value={iouThreshold}
                onChange={(e) => setIouThreshold(parseFloat(e.target.value))}
                className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#bf5af2]" />
            </div>
          </div>
        </div>

    </div>
    </div>
  );
};
