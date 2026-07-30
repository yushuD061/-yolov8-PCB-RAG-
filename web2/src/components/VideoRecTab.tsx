import React, { useRef, useState, useEffect, useCallback } from 'react';
import { Upload, Play, Pause, Settings, Brain, Sparkles, Loader2 } from 'lucide-react';

interface VideoRecTabProps {
  pushLog: (msg: string) => void;
}

export const VideoRecTab: React.FC<VideoRecTabProps> = ({ pushLog }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [confidence, setConfidence] = useState<number>(0.45);
  const [iouThreshold, setIouThreshold] = useState<number>(0.50);
  const [selectedModel, setSelectedModel] = useState<string>('yolo26n');
  const [videoKey, setVideoKey] = useState<number>(0);

  // 离线处理状态
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [processingProgress, setProcessingProgress] = useState<number>(0);
  const pollingRef = useRef<number | null>(null);

  // Gemini AI
  const [isGeminiLoading, setIsGeminiLoading] = useState<boolean>(false);
  const [geminiReport, setGeminiReport] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (videoUrl && videoRef.current) {
      const v = videoRef.current;
      v.load();
      v.play().catch(() => {});
    }
  }, [videoUrl]);

  const handleFileSelect = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    pushLog(`[上传] 开始上传: ${file.name}`);
    setIsProcessing(true);
    setProcessingProgress(0);
    setVideoUrl(null);
    setVideoKey(k => k + 1);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const uploadRes = await fetch('/api/upload', { method: 'POST', body: formData });
      const uploadData = await uploadRes.json();

      if (!uploadData.task_id) {
        pushLog('[ERROR] 上传失败');
        setIsProcessing(false);
        return;
      }

      const taskId = uploadData.task_id;
      pushLog('[处理] 视频上传完成，开始推理...');

      pollingRef.current = window.setInterval(async () => {
        try {
          const statusRes = await fetch(`/api/process/${taskId}`);
          const status = await statusRes.json();
          console.log('[Process]', status);

          if (status.percent !== undefined) {
            setProcessingProgress(status.percent);
          }

          if (status.done) {
            clearInterval(pollingRef.current!);
            pollingRef.current = null;

            if (status.url) {
              const fullUrl = `http://localhost:5000${status.url}`;
              console.log('[Video] URL:', fullUrl);
              setVideoUrl(fullUrl);
              setIsProcessing(false);
              setIsPlaying(true);
              pushLog(`[完成] 视频处理完成，已加载检测结果`);
            } else {
              pushLog(`[ERROR] 处理失败: ${status.error || '未知错误'}`);
              setIsProcessing(false);
            }
          }
        } catch (err) {
          console.error('Polling error:', err);
        }
      }, 1000);
    } catch (err) {
      pushLog('[ERROR] 上传请求失败');
      setIsProcessing(false);
    }
  }, [pushLog]);

  // Gemini AI 分析
  const runGeminiAnalysis = useCallback(async () => {
    if (!videoUrl) return;
    setIsGeminiLoading(true);
    setGeminiReport(null);
    pushLog('[AI] 正在请求 Gemini 视觉分析...');
    try {
      const res = await fetch('/api/gemini/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: null,
          prompt: '分析这段 PCB 检测视频中的缺陷情况，以中文 Markdown 回答。'
        })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        setGeminiReport(data.report);
        pushLog('[SUCCESS] Gemini 分析完成');
      }
    } catch {
      setGeminiReport('**AI 分析服务暂不可用**\n\n请稍后重试。');
      pushLog('[ERROR] Gemini 请求失败');
    } finally {
      setIsGeminiLoading(false);
    }
  }, [videoUrl, pushLog]);

  return (
    <div className="flex-1 p-6 overflow-y-auto grid grid-cols-12 gap-6 select-none">
      {/* 视频区域 */}
      <div className="col-span-12 xl:col-span-9 flex flex-col space-y-4">
        <div className="relative aspect-[16/9] bg-black rounded-xl border border-[#2c2c2e] overflow-hidden flex items-center justify-center shadow-2xl">
          {isProcessing ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/80 z-20">
              <Loader2 className="h-12 w-12 text-[#0a84ff] animate-spin mb-4" />
              <p className="text-white font-semibold text-sm mb-2">正在离线推理处理 PCB 视频...</p>
              <div className="w-64 h-2 bg-[#38383a] rounded-full overflow-hidden">
                <div
                  className="h-full bg-[#0a84ff] rounded-full transition-all duration-300"
                  style={{ width: `${processingProgress}%` }}
                />
              </div>
              <p className="text-[#8e8e93] text-xs mt-2">{processingProgress}%</p>
            </div>
          ) : videoUrl ? (
            <video
              key={videoKey}
              ref={videoRef}
              src={videoUrl}
              autoPlay
              controls
              muted
              playsInline
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="text-center text-[#8e8e93] px-6 flex flex-col items-center">
                <Upload className="h-10 w-10 text-[#0a84ff] mb-3 stroke-[1.5]" />
                <h4 className="text-sm font-semibold text-white">上传 PCB 检测视频</h4>
                <p className="text-xs text-[#8e8e93] mt-2">上传后自动进行推理，完成后播放检测结果</p>
              </div>
            </div>
          )}
        </div>

        <div className="bg-[#1c1c1e] p-4 rounded-xl border border-[#2c2c2e] flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              disabled={!videoUrl || isProcessing}
              className="px-4 py-2 bg-[#0a84ff] hover:bg-[#0a84ff]/90 disabled:opacity-40 text-white font-semibold rounded-lg text-xs cursor-pointer flex items-center space-x-2 transition"
            >
              {isProcessing ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : isPlaying ? (
                <Pause className="h-3.5 w-3.5" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              <span>{isProcessing ? '处理中' : isPlaying ? '暂停' : '播放'}</span>
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isProcessing}
              className="px-3.5 py-2 bg-transparent text-[#e5e5ea] border border-[#2c2c2e] hover:bg-white/5 disabled:opacity-40 rounded-lg text-xs font-semibold cursor-pointer transition"
            >
              上传本地视频
            </button>
            <input ref={fileInputRef} type="file" accept="video/*" className="hidden" onChange={handleFileSelect} />
          </div>

          {videoUrl && !isProcessing && (
            <span className="text-[10px] text-[#30d158] font-mono">✅ 推理完成</span>
          )}
        </div>
      </div>

      {/* 参数调节面板 */}
      <div className="col-span-12 xl:col-span-3 flex flex-col space-y-6">
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] space-y-5">
          <div className="flex items-center space-x-2 border-b border-[#2c2c2e] pb-3">
            <Settings className="h-4 w-4 text-[#0a84ff]" />
            <h3 className="text-sm font-semibold text-white">视频推理参数</h3>
          </div>

          <div className="space-y-4 text-xs">
            <div>
              <div className="flex justify-between mb-2">
                <label className="text-[#a2a2a7]">置信阈值</label>
                <span className="text-[#30d158] font-mono font-bold">{confidence.toFixed(2)}</span>
              </div>
              <input
                type="range" min="0.1" max="0.95" step="0.05"
                value={confidence}
                onChange={(e) => setConfidence(parseFloat(e.target.value))}
                className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#30d158]"
              />
            </div>

            <div>
              <div className="flex justify-between mb-2">
                <label className="text-[#a2a2a7]">交并比阈值</label>
                <span className="text-[#bf5af2] font-mono font-bold">{iouThreshold.toFixed(2)}</span>
              </div>
              <input
                type="range" min="0.1" max="0.9" step="0.05"
                value={iouThreshold}
                onChange={(e) => setIouThreshold(parseFloat(e.target.value))}
                className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#bf5af2]"
              />
            </div>

            <div>
              <label className="text-[#a2a2a7] block mb-2">推理模型</label>
              <select
                value={selectedModel}
                onChange={(e) => {
                  setSelectedModel(e.target.value);
                  pushLog(`[INFO] 切换模型: ${e.target.value}`);
                }}
                className="w-full bg-black/40 border border-[#2c2c2e] text-white p-2 rounded-lg text-xs focus:outline-none focus:border-[#0a84ff] cursor-pointer"
              >
                <option value="yolo26n">YOLO26n PCB 缺陷检测模型</option>
              </select>
            </div>
          </div>
        </div>

        {/* Gemini AI 分析 */}
        <div className="bg-[#1c1c1e] p-5 rounded-xl border border-[#2c2c2e] flex flex-col space-y-4 min-h-[200px]">
          <div className="flex items-center space-x-1.5 border-b border-[#2c2c2e] pb-2">
            <Brain className="h-4 w-4 text-[#bf5af2]" />
            <h4 className="text-xs font-semibold text-[#8e8e93] uppercase tracking-wide">Gemini AI</h4>
          </div>
          <div className="flex-1 overflow-y-auto max-h-[240px] text-xs pr-1">
            {geminiReport ? (
              <div className="text-[#f5f5f7] bg-black/40 p-4 rounded-lg border border-[#2c2c2e] whitespace-pre-wrap text-[11px]">
                {geminiReport.split('\n').map((line, idx) => (
                  <p key={idx} className={line.startsWith('**') ? 'font-bold text-[#0a84ff] mt-2' : 'text-[#cccccc]'}>{line.replace(/\*/g, '')}</p>
                ))}
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-center text-[#8e8e93]">
                <Sparkles className="h-7 w-7 text-[#bf5af2]" />
                <p className="text-[11px] mt-3">视频处理完成后可进行 AI 分析</p>
              </div>
            )}
          </div>
          <button onClick={runGeminiAnalysis} disabled={isGeminiLoading || !videoUrl}
            className="w-full py-2.5 bg-gradient-to-r from-[#0a84ff] to-[#bf5af2] hover:opacity-90 disabled:opacity-50 text-white font-bold rounded-lg text-xs cursor-pointer flex items-center justify-center space-x-2 transition">
            {isGeminiLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5 fill-white" />}
            <span>{isGeminiLoading ? '分析中...' : 'Gemini AI 分析'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
