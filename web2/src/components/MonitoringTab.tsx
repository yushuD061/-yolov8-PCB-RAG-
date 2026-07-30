import React, { useRef, useState, useEffect } from 'react';
import { Upload, Eye, EyeOff, Navigation2, ShieldAlert } from 'lucide-react';
import { SimulatedTarget, SystemConfig } from '../types';

interface MonitoringTabProps {
  targets: SimulatedTarget[];
  selectedTargetId: number | null;
  setSelectedTargetId: (id: number | null) => void;
  config: SystemConfig;
  videoFrameUrl: string | null;
  uploadedFileUrl: string | null;
  setUploadedFileUrl: (url: string | null) => void;
}

export const MonitoringTab: React.FC<MonitoringTabProps> = ({
  targets,
  selectedTargetId,
  setSelectedTargetId,
  config,
  videoFrameUrl,
  uploadedFileUrl,
  setUploadedFileUrl,
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(true);
  const [progress, setProgress] = useState<number>(0);

  const selectedTarget = targets.find((t) => t.id === selectedTargetId);

  const handleDragOver = (e: React.DragEvent) => e.preventDefault();
  
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setUploadedFileUrl(URL.createObjectURL(file));
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setUploadedFileUrl(URL.createObjectURL(e.target.files[0]));
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
      } else {
        videoRef.current.play();
      }
      setIsPlaying(!isPlaying);
    }
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const updateProgress = () => {
      setProgress((video.currentTime / video.duration) * 100 || 0);
    };

    video.addEventListener('timeupdate', updateProgress);
    return () => {
      if (video) {
        video.removeEventListener('timeupdate', updateProgress);
      }
    };
  }, [uploadedFileUrl]);

  const alarmColors = {
    none: '#0a84ff',
    amber: '#ff9f0a',
    red: '#ff453a',
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto grid grid-cols-12 gap-6">
      {/* Video Stream & Overlay Area */}
      <div className="col-span-9 flex flex-col space-y-4">
        <div
          ref={containerRef}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          className="relative aspect-[1100/620] bg-black rounded-xl overflow-hidden border border-[#2c2c2e] flex items-center justify-center select-none shadow-2xl"
        >
          {uploadedFileUrl ? (
            <video
              ref={videoRef}
              src={uploadedFileUrl}
              autoPlay
              loop
              muted
              playsInline
              className="w-full h-full object-cover"
            />
          ) : videoFrameUrl ? (
            <img src={videoFrameUrl} alt="Websocket Frame" className="w-full h-full object-cover pointer-events-none" />
          ) : (
            <div className="text-center text-[#8e8e93] p-10 flex flex-col items-center z-10">
              <Upload className="h-12 w-12 text-[#0a84ff] mb-4 stroke-[1.5]" />
              <p className="text-base font-semibold text-[#f5f5f7]">拖拽本地监控视频至此处</p>
              <p className="text-xs text-[#8e8e93] mt-2 max-w-md">
                或使用下方上传按钮导入车辆/行人多目标检测视频流。系统将自动启动 Yolov8 + Bytetrack 融合引擎。
              </p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="mt-6 px-4 py-2 bg-[#0a84ff] text-white rounded-lg text-xs font-semibold hover:bg-[#0a84ff]/90 transition cursor-pointer"
              >
                选择本地视频
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                className="hidden"
                onChange={handleFileSelect}
              />
            </div>
          )}

          {/* Symmetrical Road Grid Layers in SVG instead of Canvas */}
          <svg className="road-grid absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1100 620" preserveAspectRatio="xMidYMid slice">
            {/* Draw standard virtual grid and horizon boundaries */}
            <line x1="0" y1="200" x2="1100" y2="200" stroke="rgba(255,255,255,0.08)" />
            <text x="40" y="194" fill="#8e8e93" fontSize="10" fontFamily="monospace">HORIZON: 150m</text>
            
            {/* Symmetrical highway lanes */}
            <line x1="280" y1="200" x2="100" y2="620" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
            <line x1="480" y1="200" x2="380" y2="620" stroke="rgba(255,255,255,0.25)" strokeDasharray="10 12" strokeWidth="1.5" />
            <line x1="680" y1="200" x2="680" y2="620" stroke="rgba(255,255,255,0.25)" strokeDasharray="10 12" strokeWidth="1.5" />
            <line x1="880" y1="200" x2="980" y2="620" stroke="rgba(255,255,255,0.15)" strokeWidth="1" />
            
            {/* Safety bounds */}
            <rect x="50" y="210" width="1000" height="390" stroke="rgba(10,132,255,0.12)" fill="none" strokeWidth="1" strokeDasharray="6 8" />
            <text x="550" y="235" fill="rgba(10,132,255,0.4)" fontSize="10" textAnchor="middle" fontFamily="monospace" letterSpacing="2">
              TS-DETECTION RADAR ZONE ACTIVE • SPEED LIMIT: {config.speedLimit} KM/H
            </text>
          </svg>

          {/* Render target motion trajectories (pure SVG) */}
          {config.showTracks && (
            <svg className="trajectory-layer absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 1100 620">
              {targets.filter(t => t.trajectory && t.trajectory.length > 1).map((t) => (
                <g key={t.id}>
                  <polyline
                    points={t.trajectory.map(p => `${p.x},${p.y}`).join(' ')}
                    stroke={alarmColors[t.alarmLevel]}
                    strokeWidth="2"
                    fill="none"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="opacity-70"
                  />
                  {t.trajectory.length > 0 && (
                    <circle
                      cx={t.trajectory[t.trajectory.length - 1].x}
                      cy={t.trajectory[t.trajectory.length - 1].y}
                      r="3.5"
                      fill={alarmColors[t.alarmLevel]}
                    />
                  )}
                </g>
              ))}
            </svg>
          )}

          {/* Active Target Overlays (pure CSS / DOM) */}
          <div className="targets-overlay absolute inset-0 pointer-events-auto w-full h-full">
            {targets.map((target) => {
              const borderCol = alarmColors[target.alarmLevel];
              return (
                <div
                  key={target.id}
                  className={`target-box ${selectedTargetId === target.id ? 'selected' : ''}`}
                  style={{
                    left: `${target.x - target.width / 2}px`,
                    top: `${target.y - target.height / 2}px`,
                    width: `${target.width}px`,
                    height: `${target.height}px`,
                    '--box-color': borderCol,
                  } as React.CSSProperties}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedTargetId(target.id);
                  }}
                >
                  <span className="corner tl" />
                  <span className="corner tr" />
                  <span className="corner bl" />
                  <span className="corner br" />

                  <span className="absolute -top-6 left-0 bg-black/85 backdrop-blur-sm text-[10px] px-1.5 py-0.5 border border-white/10 rounded text-white font-mono whitespace-nowrap shadow-sm select-none pointer-events-none">
                    ID-{target.id} {target.className} {Math.round(target.speed)}km/h
                  </span>

                  {target.plate && (
                    <span className="absolute -bottom-6 left-1/2 transform -translate-x-1/2 bg-[#0a84ff] text-white font-bold text-[9px] px-1.5 py-0.2 rounded border border-white/20 whitespace-nowrap shadow-md pointer-events-none">
                      {target.plate}
                    </span>
                  )}

                  {target.alarmLevel === 'red' && (
                    <span className="absolute -top-2.5 -right-2.5 h-4.5 w-4.5 rounded-full bg-[#ff453a] flex items-center justify-center text-white text-[9px] font-bold border border-white/20 animate-bounce pointer-events-none">
                      !
                    </span>
                  )}
                </div>
              );
            })}
          </div>

          <div className="absolute top-4 left-4 flex space-x-2">
            <span className="bg-black/75 backdrop-blur-md px-3 py-1 rounded text-xs border border-white/10 text-white font-semibold font-sans">
              CAMERA_01_FEED
            </span>
            <span className="bg-[#30d158]/20 backdrop-blur-md px-3 py-1 rounded text-xs border border-[#30d158]/30 text-[#30d158] font-bold">
              LIVE ANALYTICS
            </span>
          </div>
        </div>

        {/* Local Video Controls */}
        {uploadedFileUrl && (
          <div className="bg-[#1c1c1e] p-4 rounded-xl border border-[#2c2c2e] flex items-center space-x-4 select-none">
            <button
              onClick={togglePlay}
              className="px-4 py-2 bg-[#0a84ff] hover:bg-[#0a84ff]/90 text-white rounded-lg text-xs font-semibold cursor-pointer"
            >
              {isPlaying ? '暂停推理' : '继续推理'}
            </button>
            <div className="flex-1 h-2 bg-black/40 rounded-full overflow-hidden relative">
              <div
                className="h-full bg-[#0a84ff] transition-all duration-100"
                style={{ width: `${progress}%` }}
              />
            </div>
            <button
              onClick={() => setUploadedFileUrl(null)}
              className="px-3 py-2 bg-transparent border border-[#ff453a]/30 text-[#ff453a] hover:bg-[#ff453a]/10 rounded-lg text-xs font-semibold cursor-pointer"
            >
              释放视频
            </button>
          </div>
        )}
      </div>

      {/* Target telemetry telemetry panels */}
      <div className="col-span-3 flex flex-col space-y-6 select-none">
        {/* Detail Panel */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] flex flex-col h-[320px]">
          <h3 className="text-sm font-semibold mb-4 text-[#8e8e93] tracking-wider uppercase font-sans">
            目标数据遥测
          </h3>
          {selectedTarget ? (
            <div className="flex-1 flex flex-col justify-between">
              <div className="space-y-3 font-mono text-sm">
                <div className="flex justify-between py-1.5 border-b border-[#2c2c2e]">
                  <span className="text-[#8e8e93]">目标类别:</span>
                  <span className="font-bold text-[#0a84ff]">{selectedTarget.className}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[#2c2c2e]">
                  <span className="text-[#8e8e93]">追踪 ID:</span>
                  <span className="font-bold text-white">#{selectedTarget.id}</span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[#2c2c2e]">
                  <span className="text-[#8e8e93]">实时车速:</span>
                  <span className={`font-bold ${selectedTarget.speed > config.speedLimit ? 'text-[#ff453a]' : 'text-[#30d158]'}`}>
                    {Math.round(selectedTarget.speed)} km/h
                  </span>
                </div>
                <div className="flex justify-between py-1.5 border-b border-[#2c2c2e]">
                  <span className="text-[#8e8e93]">测距(米):</span>
                  <span className="font-bold text-[#bf5af2]">{selectedTarget.distance.toFixed(1)}m</span>
                </div>
                {selectedTarget.plate && (
                  <div className="flex justify-between py-1.5 border-b border-[#2c2c2e]">
                    <span className="text-[#8e8e93]">车牌识别:</span>
                    <span className="font-bold text-white bg-[#0a84ff]/30 px-1.5 rounded">{selectedTarget.plate}</span>
                  </div>
                )}
                <div className="flex justify-between py-1.5">
                  <span className="text-[#8e8e93]">安全评级:</span>
                  <span className={`font-bold uppercase ${selectedTarget.alarmLevel === 'red' ? 'text-[#ff453a]' : selectedTarget.alarmLevel === 'amber' ? 'text-[#ff9f0a]' : 'text-[#30d158]'}`}>
                    {selectedTarget.alarmLevel === 'none' ? 'SAFE' : selectedTarget.alarmLevel}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedTargetId(null)}
                className="w-full py-2 bg-[#2c2c2e] hover:bg-[#3a3a3c] text-[#f5f5f7] rounded-lg text-xs font-semibold transition mt-3 cursor-pointer"
              >
                清除追踪
              </button>
            </div>
          ) : (
            <div className="flex-1 flex flex-col items-center justify-center text-center text-[#8e8e93]">
              <Navigation2 className="h-8 w-8 text-[#2c2c2e] mb-2 rotate-45" />
              <p className="text-xs">在视频雷达区或下方队列中点击任意目标，即可追踪感知实况数据。</p>
            </div>
          )}
        </div>

        {/* Algorithm config indicators */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] flex flex-col justify-between h-[276px]">
          <div>
            <h3 className="text-sm font-semibold mb-4 text-[#8e8e93] tracking-wider uppercase font-sans">
              算法运行参数
            </h3>
            <div className="space-y-3 font-mono text-xs">
              <div className="flex justify-between text-[#8e8e93]">
                <span>限速警示值:</span>
                <span className="text-white font-bold">{config.speedLimit} km/h</span>
              </div>
              <div className="flex justify-between text-[#8e8e93]">
                <span>置信阈值:</span>
                <span className="text-white font-bold">{config.confidence}</span>
              </div>
              <div className="flex justify-between text-[#8e8e93]">
                <span>重叠率 (IoU):</span>
                <span className="text-white font-bold">{config.iouThreshold}</span>
              </div>
              <div className="flex justify-between text-[#8e8e93]">
                <span>轨迹层绘制:</span>
                <span className="text-white font-bold flex items-center space-x-1">
                  {config.showTracks ? <Eye className="h-3 w-3 inline" /> : <EyeOff className="h-3 w-3 inline" />}
                  <span>{config.showTracks ? '开启' : '关闭'}</span>
                </span>
              </div>
            </div>
          </div>

          <div className="border-t border-[#2c2c2e] pt-4">
            <div className="flex items-start space-x-2 text-[11px] text-[#ff453a] bg-[#ff453a]/10 p-2.5 rounded border border-[#ff453a]/20">
              <ShieldAlert className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              <span>注意：限速规则与去重参数对当前捕获链路及边缘推理卡即时生效。</span>
            </div>
          </div>
        </div>
      </div>

      {/* Grid Table Stream list */}
      <div className="col-span-12 bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#2c2c2e] flex justify-between items-center select-none">
          <h3 className="text-sm font-semibold text-[#8e8e93] tracking-wider uppercase font-sans">
            实时检测目标队列 ({targets.length})
          </h3>
          <span className="text-xs text-[#8e8e93] font-mono">更新频度: 100ms / 10Hz</span>
        </div>
        <div className="max-h-[220px] overflow-y-auto">
          <table className="w-full text-left border-collapse text-xs font-mono">
            <thead className="sticky top-0 bg-[#2c2c2e] text-[#8e8e93] font-bold select-none z-10">
              <tr>
                <th className="px-6 py-3">ID</th>
                <th className="px-6 py-3">类别</th>
                <th className="px-6 py-3">测距 (距离)</th>
                <th className="px-6 py-3">实时速度</th>
                <th className="px-6 py-3">车牌</th>
                <th className="px-6 py-3">报警状态</th>
                <th className="px-6 py-3">车道</th>
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
                  <td className="px-6 py-3 text-[#a2a2a7]">{t.className}</td>
                  <td className="px-6 py-3 text-[#bf5af2]">{t.distance.toFixed(1)}m</td>
                  <td className={`px-6 py-3 font-semibold ${t.speed > config.speedLimit ? 'text-[#ff453a]' : 'text-[#30d158]'}`}>
                    {Math.round(t.speed)} km/h
                  </td>
                  <td className="px-6 py-3">
                    {t.plate ? <span className="bg-[#0a84ff]/20 text-[#0a84ff] px-2 py-0.5 rounded font-bold">{t.plate}</span> : '--'}
                  </td>
                  <td className="px-6 py-3">
                    <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase ${
                      t.alarmLevel === 'red' ? 'bg-[#ff453a]/20 text-[#ff453a]' : t.alarmLevel === 'amber' ? 'bg-[#ff9f0a]/20 text-[#ff9f0a]' : 'bg-white/10 text-white'
                    }`}>
                      {t.alarmLevel === 'none' ? 'normal' : t.alarmLevel}
                    </span>
                  </td>
                  <td className="px-6 py-3 text-white">车道 {t.lane}</td>
                </tr>
              ))}
              {targets.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-[#8e8e93]">
                    暂未捕获到监控流目标。请等待模拟触发，或拖拽导入监控视频。
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
