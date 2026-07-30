import React from 'react';
import { Cpu, HardDrive, Thermometer, AlertTriangle, Sliders, Download } from 'lucide-react';
import { SystemConfig } from '../types';

interface ConfigTabProps {
  config: SystemConfig;
  updateConfig: (cfg: Partial<SystemConfig>) => void;
}

export const ConfigTab: React.FC<ConfigTabProps> = ({ config, updateConfig }) => {
  const exportConfig = () => {
    const data = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(config, null, 2));
    const a = document.createElement('a');
    a.setAttribute("href", data);
    a.setAttribute("download", "pcb_system_config.json");
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto max-w-5xl space-y-8 select-none">
      <div>
        <h2 className="text-xl font-bold text-white mb-2 font-sans">系统配置</h2>
        <p className="text-sm text-[#8e8e93]">
          全局设置项，各检测 Tab 中的置信度 / IoU 为独立调节，此处不重复。
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* ── 模型配置 ── */}
        <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
            <Sliders className="h-5 w-5 text-[#0a84ff]" />
            <h3 className="text-base font-semibold text-white">模型配置</h3>
          </div>
<div>
            <label className="block text-xs text-[#a2a2a7] font-semibold mb-2">推理模型</label>
            <select value={config.selectedModel}
              onChange={(e) => updateConfig({ selectedModel: e.target.value })}
              className="w-full bg-black/40 border border-[#2c2c2e] text-xs text-white p-2.5 rounded-lg focus:outline-none focus:border-[#0a84ff] cursor-pointer">
              <option value="yolo26n">YOLO26n — PCB 缺陷检测</option>
              <option value="yolon8_best">YOLOv8 Best — PCB 缺陷检测</option>
            </select>
            <p className="text-[10px] text-[#8e8e93] mt-2">切换后实时检测管线将自动重载模型</p>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <label className="text-xs text-[#a2a2a7] font-semibold">PC 端本地 YOLO 推理</label>
              <p className="text-[10px] text-[#8e8e93] mt-1">
                关闭（默认）= 板端 RV1126B 推理，PC 仅做统计转发；开启 = PC 直接跑模型推理
              </p>
            </div>
            <button onClick={() => updateConfig({ localInference: !config.localInference })}
              className={`w-10 h-5 rounded-full transition-colors relative shrink-0 ${config.localInference ? 'bg-[#30d158]' : 'bg-[#48484a]'}`}>
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${config.localInference ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>
        </div>

        {/* ── 检测存储 ── */}
        <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
            <HardDrive className="h-5 w-5 text-[#30d158]" />
            <h3 className="text-base font-semibold text-white">检测存储</h3>
          </div>

          <div className="flex items-center justify-between">
            <label className="text-xs text-[#a2a2a7] font-semibold">自动保存检测结果</label>
            <button onClick={() => updateConfig({ saveResults: !config.saveResults })}
              className={`w-10 h-5 rounded-full transition-colors relative ${config.saveResults ? 'bg-[#30d158]' : 'bg-[#48484a]'}`}>
              <span className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${config.saveResults ? 'translate-x-5' : 'translate-x-0.5'}`} />
            </button>
          </div>

          <div className={!config.saveResults ? 'opacity-40' : ''}>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">结果保留天数</label>
              <span className="text-sm font-bold text-[#0a84ff] font-mono">{config.retentionDays} 天</span>
            </div>
            <input type="range" min="7" max="180" step="1" value={config.retentionDays} disabled={!config.saveResults}
              onChange={(e) => updateConfig({ retentionDays: parseInt(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#0a84ff]" />
            <p className="text-[10px] text-[#8e8e93] mt-1">超过期限的检测结果将被自动清理</p>
          </div>

          <div className={!config.saveResults ? 'opacity-40' : ''}>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">图像保存质量</label>
              <span className="text-sm font-bold text-[#bf5af2] font-mono">{config.jpegQuality}%</span>
            </div>
            <input type="range" min="50" max="100" step="5" value={config.jpegQuality} disabled={!config.saveResults}
              onChange={(e) => updateConfig({ jpegQuality: parseInt(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#bf5af2]" />
          </div>
        </div>

        {/* ── RV1126B 板端配置 ── */}
        <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
            <Cpu className="h-5 w-5 text-[#ff9f0a]" />
            <h3 className="text-base font-semibold text-white">RV1126B 板端参数</h3>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">最大推理帧率</label>
              <span className="text-sm font-bold text-[#ff9f0a] font-mono">{config.maxFps} FPS</span>
            </div>
            <input type="range" min="15" max="60" step="5" value={config.maxFps}
              onChange={(e) => updateConfig({ maxFps: parseInt(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#ff9f0a]" />
            <p className="text-[10px] text-[#8e8e93] mt-1">降低帧率可减少 NPU 负载和板端温度</p>
          </div>

          <div>
            <label className="block text-xs text-[#a2a2a7] font-semibold mb-2">NPU 频率模式</label>
            <div className="grid grid-cols-3 gap-2">
              {(['powersave', 'balanced', 'performance'] as const).map((mode) => (
                <button key={mode}
                  onClick={() => updateConfig({ npuMode: mode })}
                  className={`py-1.5 rounded text-[10px] font-semibold border transition cursor-pointer ${
                    config.npuMode === mode
                      ? 'bg-[#ff9f0a]/20 border-[#ff9f0a]/50 text-[#ff9f0a]'
                      : 'bg-black/40 border-[#2c2c2e] text-[#8e8e93] hover:border-[#ff9f0a]/30'
                  }`}>
                  {mode === 'powersave' ? '节能' : mode === 'balanced' ? '均衡' : '性能'}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">温度告警阈值</label>
              <span className="text-sm font-bold text-[#ff9f0a] font-mono">{config.tempWarning}°C</span>
            </div>
            <input type="range" min="60" max="95" step="5" value={config.tempWarning}
              onChange={(e) => updateConfig({ tempWarning: parseInt(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#ff9f0a]" />
          </div>
        </div>

        {/* ── 告警与通知 ── */}
        <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
            <AlertTriangle className="h-5 w-5 text-[#ff453a]" />
            <h3 className="text-base font-semibold text-white">告警与通知</h3>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">复查置信度阈值</label>
              <span className="text-sm font-bold text-[#ff453a] font-mono">{config.reviewThreshold.toFixed(2)}</span>
            </div>
            <input type="range" min="0.1" max="0.8" step="0.05" value={config.reviewThreshold}
              onChange={(e) => updateConfig({ reviewThreshold: parseFloat(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#ff453a]" />
            <p className="text-[10px] text-[#8e8e93] mt-1">低于此值的缺陷检测结果将被标记为「需人工复查」</p>
          </div>

          <div>
            <div className="flex justify-between mb-2">
              <label className="text-xs text-[#a2a2a7] font-semibold">连续缺陷告警</label>
              <span className="text-sm font-bold text-[#ff453a] font-mono">{config.consecutiveAlerts} 次</span>
            </div>
            <input type="range" min="3" max="20" step="1" value={config.consecutiveAlerts}
              onChange={(e) => updateConfig({ consecutiveAlerts: parseInt(e.target.value) })}
              className="w-full h-1 bg-black rounded-lg appearance-none cursor-pointer accent-[#ff453a]" />
            <p className="text-[10px] text-[#8e8e93] mt-1">连续检测到缺陷超过此数时触发告警通知</p>
          </div>
        </div>
      </div>

      {/* ── 系统信息 ── */}
      <div className="bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] space-y-4">
        <div className="flex items-center space-x-3 border-b border-[#2c2c2e] pb-4">
          <HardDrive className="h-5 w-5 text-[#0a84ff]" />
          <h3 className="text-base font-semibold text-white">系统信息</h3>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
          <div className="bg-black/30 p-4 rounded-lg border border-[#2c2c2e] space-y-2">
            <p className="text-[#8e8e93] text-[10px] uppercase tracking-wider">软件版本</p>
            <p className="text-white font-semibold">PCB 缺陷检测系统 v1.0.0</p>
            <p className="text-[#8e8e93]">前端 React 19 + Vite 6</p>
          </div>
          <div className="bg-black/30 p-4 rounded-lg border border-[#2c2c2e] space-y-2">
            <p className="text-[#8e8e93] text-[10px] uppercase tracking-wider">推理引擎</p>
            <p className="text-white font-semibold">{config.selectedModel || '未加载'}</p>
            <p className="text-[#8e8e93]">Ultralytics YOLO + RV1126B NPU</p>
          </div>
          <div className="bg-black/30 p-4 rounded-lg border border-[#2c2c2e] space-y-2">
            <p className="text-[#8e8e93] text-[10px] uppercase tracking-wider">缺陷类型</p>
            <p className="text-white font-semibold">6 类 PCB 缺陷</p>
            <p className="text-[#8e8e93]">漏孔 / 鼠咬 / 开路 / 短路 / 毛刺 / 残铜</p>
          </div>
        </div>
        <div className="flex justify-end pt-2">
          <button onClick={exportConfig}
            className="flex items-center space-x-2 px-4 py-2 bg-[#2c2c2e] hover:bg-[#3a3a3c] text-white rounded-lg text-xs font-semibold transition cursor-pointer">
            <Download className="h-4 w-4" />
            <span>导出配置</span>
          </button>
        </div>
      </div>
    </div>
  );
};
