import React, { useState, useRef, useCallback } from 'react';
import { Upload, Image as ImageIcon, Sparkles, Settings, Loader2, CheckCircle2, XCircle } from 'lucide-react';

interface ImageRecTabProps {
  pushLog: (msg: string) => void;
  onDetect?: (result: {
    detections: Array<{class_id: number; className: string; confidence: number}>;
    itemName: string;
    source: 'image';
    batchId: string;
  }) => void;
}

interface DetectedObject {
  class_id: number;
  className: string;
  confidence: number;
  x1: number; y1: number;
  x2: number; y2: number;
  width: number; height: number;
}

interface BatchItem {
  id: string;
  file: File;
  preview: string;
  status: 'pending' | 'detecting' | 'done' | 'error';
  detections: DetectedObject[];
  errorMsg?: string;
}

import { getDefectNameCn } from '../types';

const DEFECT_COLORS: Record<string, string> = {
  missing_hole: '#ff453a', mouse_bite: '#ff9f0a', open_circuit: '#bf5af2',
  short: '#0a84ff', spur: '#30d158', spurious_copper: '#ffd60a',
};
const DEFECT_CLASS_IDS: Record<number, string> = {
  0: 'missing_hole', 1: 'mouse_bite', 2: 'open_circuit',
  3: 'short', 4: 'spur', 5: 'spurious_copper',
};

export const ImageRecTab: React.FC<ImageRecTabProps> = ({ pushLog, onDetect }) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [isBatchDetecting, setIsBatchDetecting] = useState(false);
  const [batchProgress, setBatchProgress] = useState({ done: 0, total: 0 });

  const [confidence, setConfidence] = useState<number>(0.45);
  const [iouThreshold, setIouThreshold] = useState<number>(0.50);
  const [selectedModel, setSelectedModel] = useState<string>('yolo26n');

  const getDefectColor = (cid: number) => DEFECT_COLORS[DEFECT_CLASS_IDS[cid]] || '#0a84ff';
  const getLocalDefectNameCn = (cid: number) => getDefectNameCn(DEFECT_CLASS_IDS[cid] || '');
  const getDefectName = (cid: number) => DEFECT_CLASS_IDS[cid] || 'unknown';

  // 计算图片显示尺寸
  const [displayDims, setDisplayDims] = useState<{ w: number; h: number } | null>(null);
  const onImgLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    const nw = img.naturalWidth, nh = img.naturalHeight;
    const maxW = window.innerWidth * 0.48, maxH = window.innerHeight * 0.55;
    let dw = nw, dh = nh;
    if (dw > maxW) { dh = dh * maxW / dw; dw = maxW; }
    if (dh > maxH) { dw = dw * maxH / dh; dh = maxH; }
    setDisplayDims({ w: Math.round(dw), h: Math.round(dh) });
  }, []);

  // 添加图片
  const addImages = useCallback((files: FileList) => {
    const newItems: BatchItem[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (!file.type.startsWith('image/')) continue;
      const id = `img-${Date.now()}-${i}`;
      newItems.push({ id, file, preview: URL.createObjectURL(file), status: 'pending', detections: [] });
      pushLog(`[上传] ${file.name}`);
    }
    setItems((prev) => [...prev, ...newItems]);
    if (newItems.length > 0 && !activeId) setActiveId(newItems[0].id);
  }, [pushLog, activeId]);

  const handleDrop = (e: React.DragEvent) => { e.preventDefault(); if (e.dataTransfer.files) addImages(e.dataTransfer.files); };
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => { if (e.target.files) addImages(e.target.files); };
  const removeItem = (id: string) => {
    setItems((prev) => prev.filter((it) => it.id !== id));
    if (activeId === id) setActiveId(null);
  };
  const clearAll = () => { setItems([]); setActiveId(null); };

  // 单张检测
  const detectOne = useCallback(async (item: BatchItem): Promise<DetectedObject[]> => {
    const formData = new FormData();
    formData.append('file', item.file);
    formData.append('confidence', confidence.toString());
    formData.append('iou', iouThreshold.toString());
    const res = await fetch('/api/detect/image', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    return data.detections || [];
  }, [confidence, iouThreshold]);

  // 批量检测
  const runBatchDetection = useCallback(async () => {
    const pending = items.filter((it) => it.status === 'pending');
    if (pending.length === 0) { pushLog('[检测] 没有待检测的图片'); return; }
    setIsBatchDetecting(true);
    setBatchProgress({ done: 0, total: pending.length });
    pushLog(`[检测] 开始批量检测 ${pending.length} 张图片...`);
    const batchId = `BATCH-${new Date().toISOString().replace(/[-:TZ.]/g, '').slice(0, 14)}`;

    for (const item of pending) {
      setItems((prev) => prev.map((it) => it.id === item.id ? { ...it, status: 'detecting' as const, detections: [] } : it));
      try {
        const dets = await detectOne(item);
        setItems((prev) => prev.map((it) => it.id === item.id ? { ...it, status: 'done' as const, detections: dets } : it));
        onDetect?.({ detections: dets, itemName: item.file.name, source: 'image', batchId });
        pushLog(`[检测] ${item.file.name}: ${dets.length} 处缺陷`);
      } catch (err: any) {
        setItems((prev) => prev.map((it) => it.id === item.id ? { ...it, status: 'error' as const, errorMsg: err.message } : it));
        pushLog(`[ERROR] ${item.file.name}: ${err.message}`);
      }
      setBatchProgress((prev) => ({ ...prev, done: prev.done + 1 }));
    }
    setIsBatchDetecting(false);
    pushLog(`[检测] 批量检测完成，批次 ${batchId}`);
  }, [items, detectOne, pushLog, onDetect]);

  const activeItem = items.find((it) => it.id === activeId);
  const totalDefects = items.reduce((s, it) => s + (it.detections?.length || 0), 0);
  const stats = () => {
    const counts: Record<string, number> = {};
    items.forEach((it) => (it.detections || []).forEach((d) => { const n = getDefectName(d.class_id); counts[n] = (counts[n] || 0) + 1; }));
    return counts;
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto grid grid-cols-12 gap-6 select-none">
      {/* 左侧：图片列表 */}
      <div className="col-span-12 lg:col-span-3 flex flex-col space-y-3">
        <div className="bg-[#1c1c1e] p-3 rounded-xl border border-[#2c2c2e]">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs text-[#8e8e93] font-semibold">图片列表 ({items.length})</span>
            <div className="flex space-x-2">
              {items.length > 0 && <button onClick={clearAll} className="text-[10px] text-[#ff453a] hover:text-white transition cursor-pointer">清空</button>}
              <button onClick={() => fileInputRef.current?.click()} className="text-[10px] text-[#0a84ff] hover:text-white transition cursor-pointer">+ 添加</button>
            </div>
          </div>
          <div className="space-y-2 max-h-[55vh] overflow-y-auto pr-1">
            {items.map((item) => (
              <div key={item.id}
                onClick={() => { setActiveId(item.id); }}
                className={`flex items-center space-x-2 p-2 rounded-lg cursor-pointer border transition ${
                  activeId === item.id ? 'bg-[#0a84ff]/10 border-[#0a84ff]/30' : 'bg-black/30 border-transparent hover:border-[#2c2c2e]'
                }`}>
                <div className="w-10 h-10 rounded overflow-hidden shrink-0 bg-black">
                  <img src={item.preview} className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] text-white truncate">{item.file.name}</p>
                  <div className="flex items-center space-x-1 mt-0.5">
                    {item.status === 'pending' && <span className="text-[9px] text-[#8e8e93]">待检测</span>}
                    {item.status === 'detecting' && <Loader2 className="h-2.5 w-2.5 text-[#0a84ff] animate-spin" />}
                    {item.status === 'done' && <><CheckCircle2 className="h-2.5 w-2.5 text-[#30d158]" /><span className="text-[9px] text-[#30d158]">{item.detections?.length || 0} 处</span></>}
                    {item.status === 'error' && <XCircle className="h-2.5 w-2.5 text-[#ff453a]" />}
                  </div>
                </div>
                <button onClick={(e) => { e.stopPropagation(); removeItem(item.id); }} className="text-[#8e8e93] hover:text-[#ff453a] transition cursor-pointer shrink-0"><XCircle className="h-3 w-3" /></button>
              </div>
            ))}
            {items.length === 0 && (
              <div className="text-center py-8 text-[#8e8e93] text-xs">拖拽或点击添加图片</div>
            )}
          </div>
        </div>

        {/* 批量操作 */}
        <div className="bg-[#1c1c1e] p-3 rounded-xl border border-[#2c2c2e] space-y-2">
          <button onClick={runBatchDetection} disabled={isBatchDetecting || items.filter((it) => it.status === 'pending').length === 0}
            className="w-full py-2 bg-[#30d158] hover:bg-[#30d158]/90 disabled:opacity-40 text-black font-bold rounded-lg text-xs cursor-pointer transition flex items-center justify-center space-x-1">
            {isBatchDetecting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            <span>{isBatchDetecting ? `检测中 ${batchProgress.done}/${batchProgress.total}` : '批量检测全部'}</span>
          </button>
          {items.length > 0 && (
            <div className="text-[10px] text-[#8e8e93] text-center">
              总计 {totalDefects} 处缺陷 · 待检测 {items.filter((it) => it.status === 'pending').length} 张
            </div>
          )}
        </div>

        {/* 检测参数 */}
        <div className="bg-[#1c1c1e] p-3 rounded-xl border border-[#2c2c2e] space-y-3">
          <div className="flex items-center space-x-1 border-b border-[#2c2c2e] pb-2"><Settings className="h-3 w-3 text-[#0a84ff]" /><span className="text-xs font-semibold text-white">参数</span></div>
          <div><div className="flex justify-between mb-1"><label className="text-[10px] text-[#a2a2a7]">置信阈值</label><span className="text-[10px] text-[#30d158] font-mono font-bold">{confidence.toFixed(2)}</span></div>
            <input type="range" min="0.1" max="0.95" step="0.05" value={confidence} onChange={(e) => setConfidence(parseFloat(e.target.value))} className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#30d158]" /></div>
          <div><div className="flex justify-between mb-1"><label className="text-[10px] text-[#a2a2a7]">交并比阈值</label><span className="text-[10px] text-[#bf5af2] font-mono font-bold">{iouThreshold.toFixed(2)}</span></div>
            <input type="range" min="0.1" max="0.9" step="0.05" value={iouThreshold} onChange={(e) => setIouThreshold(parseFloat(e.target.value))} className="w-full h-1 bg-black/40 rounded-lg appearance-none cursor-pointer accent-[#bf5af2]" /></div>
        </div>
      </div>

      {/* 中间：预览 + 检测框 + 缺陷详情 */}
      <div className="col-span-12 lg:col-span-9 flex flex-col space-y-3">
        <div
          onDragOver={(e) => e.preventDefault()} onDrop={handleDrop}
          className="relative bg-[#0c0c0e] rounded-xl overflow-hidden border border-[#2c2c2e] shadow-2xl flex items-center justify-center"
          style={displayDims ? { width: displayDims.w, height: displayDims.h, margin: '0 auto' } : { aspectRatio: '4/3', maxHeight: '55vh', minHeight: '280px' }}>
          {activeItem && activeItem.preview ? (
            <>
              <img src={activeItem.preview} alt="" onLoad={onImgLoad} className="absolute inset-0 w-full h-full object-fill" />
              {activeItem.detections?.map((d, idx) => {
                const color = getDefectColor(d.class_id);
                return (
                  <div key={idx} className="absolute border-2 cursor-pointer z-10 opacity-85 hover:opacity-100 hover:brightness-110"
                    style={{ left: `${d.x1}%`, top: `${d.y1}%`, width: `${d.width}%`, height: `${d.height}%`, borderColor: color, boxShadow: `0 0 8px ${color}` }}>
                    <span className="absolute -top-5 left-0 text-[8px] px-1 py-0.5 rounded font-bold whitespace-nowrap text-white" style={{ backgroundColor: color }}>
                      {getLocalDefectNameCn(d.class_id)} {Math.round(d.confidence * 100)}%
                    </span>
                  </div>
                );
              })}
              {activeItem.status === 'detecting' && (
                <div className="absolute inset-0 bg-black/50 flex items-center justify-center z-20"><Loader2 className="h-8 w-8 text-[#0a84ff] animate-spin" /></div>
              )}
            </>
          ) : (
            <div className="flex flex-col items-center justify-center text-center p-6 h-full w-full">
              <ImageIcon className="h-10 w-10 text-[#2c2c2e] mb-2 stroke-[1.2]" />
              <p className="text-xs text-[#8e8e93]">拖拽或选择图片</p>
              <p className="text-[10px] text-[#8e8e93] mt-1">支持批量上传 JPEG/PNG</p>
            </div>
          )}
        </div>
        <input ref={fileInputRef} type="file" multiple accept="image/*" className="hidden" onChange={handleFileSelect} />

        {/* 缺陷统计 */}
        {totalDefects > 0 && (
          <div className="bg-[#1c1c1e] p-2 rounded-xl border border-[#2c2c2e]">
            <div className="flex flex-wrap gap-1.5">
              {Object.entries(stats()).map(([name, count]) => (
                <span key={name} className="inline-flex items-center space-x-1 text-[9px] px-1.5 py-0.5 rounded-full font-bold"
                  style={{ backgroundColor: (DEFECT_COLORS[name] || '#0a84ff') + '20', color: DEFECT_COLORS[name] || '#0a84ff' }}>
                  <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: DEFECT_COLORS[name] || '#0a84ff' }} />
                  <span>{getDefectNameCn(name)}: {count}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* 缺陷详情 */}
        <div className="bg-[#1c1c1e] p-3 rounded-xl border border-[#2c2c2e]">
          <h4 className="text-[10px] font-semibold text-[#8e8e93] uppercase tracking-wide border-b border-[#2c2c2e] pb-2 mb-2">缺陷详情</h4>
          {activeItem && activeItem.detections?.length > 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px] font-mono">
              {activeItem.detections.slice(0, 10).map((d, i) => (
                <div key={i} className="bg-black/30 p-2 rounded-lg border border-[#2c2c2e] flex flex-col items-center">
                  <span className="font-bold text-[11px]" style={{ color: getDefectColor(d.class_id) }}>{getLocalDefectNameCn(d.class_id)}</span>
                  <span className="text-[9px] text-[#30d158]">{(d.confidence * 100).toFixed(1)}%</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-4 text-[#8e8e93] text-[11px]">
              {activeItem ? '点击「批量检测全部」' : '请先添加图片'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
