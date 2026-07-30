import React, { useState } from 'react';
import { Search, Trash2, Calendar, Clock, ArrowUpRight, RotateCcw, Layers3 } from 'lucide-react';
import { AlarmEvent } from '../types';

interface HistoryTabProps {
  alarms: AlarmEvent[];
  clearAlarms: () => void;
}

const DEFECT_CLASS_DESCRIPTIONS = [
  { id: 0, code: 'missing_hole', name: '漏孔' },
  { id: 1, code: 'mouse_bite', name: '鼠咬' },
  { id: 2, code: 'open_circuit', name: '开路' },
  { id: 3, code: 'short', name: '短路' },
  { id: 4, code: 'spur', name: '毛刺' },
  { id: 5, code: 'spurious_copper', name: '残铜' },
];

function resolveDefectClassId(record: AlarmEvent): number {
  if (record.source !== 'image' || record.type !== 'defect') return record.targetId;
  const byClassName = DEFECT_CLASS_DESCRIPTIONS.find(
    (item) => item.code === record.className,
  );
  if (byClassName) return byClassName.id;
  const byDescription = DEFECT_CLASS_DESCRIPTIONS.find(
    (item) => record.description.includes(item.name) || record.description.includes(item.code),
  );
  return byDescription?.id ?? record.targetId;
}

export const HistoryTab: React.FC<HistoryTabProps> = ({ alarms, clearAlarms }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedAlarm, setSelectedAlarm] = useState<AlarmEvent | null>(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [selectedBatch, setSelectedBatch] = useState('all');

  const batchOptions = Array.from(
    new Set(alarms.map((alarm) => alarm.batchId || 'legacy')),
  ).sort().reverse();

  const filteredAlarms = alarms.filter((a) => {
    const matchesSearch =
      a.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      resolveDefectClassId(a).toString().includes(searchTerm);
    const eventTime = new Date(a.timestamp).getTime();
    const startTime = startDate ? new Date(`${startDate}T00:00:00`).getTime() : null;
    const endTime = endDate ? new Date(`${endDate}T23:59:59.999`).getTime() : null;
    const matchesStart = startTime === null || eventTime >= startTime;
    const matchesEnd = endTime === null || eventTime <= endTime;
    const alarmBatch = a.batchId || 'legacy';
    const matchesBatch = selectedBatch === 'all' || alarmBatch === selectedBatch;
    return matchesSearch && matchesStart && matchesEnd && matchesBatch;
  });

  const resetFilters = () => {
    setSearchTerm('');
    setStartDate('');
    setEndDate('');
    setSelectedBatch('all');
  };

  return (
    <div className="flex-1 min-h-0 p-6 overflow-hidden grid grid-cols-12 gap-6">
      <div className="col-span-8 min-h-0 flex flex-col space-y-4">
        <div className="bg-[#1c1c1e] p-4 rounded-xl border border-[#2c2c2e] space-y-3 select-none">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-[#8e8e93]" />
            <input
              type="text"
              placeholder="搜索目标 ID 或事件详情..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-black/40 border border-[#2c2c2e] text-[#f5f5f7] rounded-lg pl-10 pr-4 py-2 text-sm focus:outline-none focus:border-[#0a84ff]"
            />
          </div>

          <div className="flex space-x-3">
            <button
              onClick={clearAlarms}
              className="flex items-center space-x-2 px-4 py-2 border border-[#ff453a]/20 bg-[#ff453a]/10 hover:bg-[#ff453a]/20 text-[#ff453a] rounded-lg text-sm font-semibold transition cursor-pointer"
            >
              <Trash2 className="h-4 w-4" />
              <span>清空记录</span>
            </button>
          </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 pt-3 border-t border-[#2c2c2e]">
            <label className="space-y-1">
              <span className="text-[10px] text-[#8e8e93] flex items-center gap-1"><Calendar className="h-3 w-3" />开始日期</span>
              <input type="date" value={startDate} max={endDate || undefined}
                onChange={(e) => setStartDate(e.target.value)}
                className="w-full bg-black/40 border border-[#2c2c2e] text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#0a84ff]" />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-[#8e8e93] flex items-center gap-1"><Calendar className="h-3 w-3" />结束日期</span>
              <input type="date" value={endDate} min={startDate || undefined}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full bg-black/40 border border-[#2c2c2e] text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#0a84ff]" />
            </label>
            <label className="space-y-1">
              <span className="text-[10px] text-[#8e8e93] flex items-center gap-1"><Layers3 className="h-3 w-3" />检测批次</span>
              <select value={selectedBatch} onChange={(e) => setSelectedBatch(e.target.value)}
                className="w-full bg-black/40 border border-[#2c2c2e] text-white rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-[#0a84ff]">
                <option value="all">全部批次</option>
                {batchOptions.map((batch) => (
                  <option key={batch} value={batch}>{batch === 'legacy' ? '历史记录（无批次）' : batch}</option>
                ))}
              </select>
            </label>
            <div className="flex items-end">
              <button onClick={resetFilters}
                className="w-full flex items-center justify-center gap-2 px-3 py-2 border border-[#2c2c2e] hover:bg-white/5 text-[#8e8e93] hover:text-white rounded-lg text-xs transition cursor-pointer">
                <RotateCcw className="h-3.5 w-3.5" />重置筛选
              </button>
            </div>
          </div>
        </div>

        <div className="bg-[#1c1c1e] rounded-xl border border-[#2c2c2e] overflow-hidden flex-1 min-h-0 flex flex-col">
          <div className="px-6 py-4 border-b border-[#2c2c2e] select-none">
            <h3 className="text-sm font-semibold text-[#8e8e93] tracking-wider uppercase font-sans">
              缺陷检测记录 ({filteredAlarms.length})
            </h3>
          </div>
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
            <div className="divide-y divide-[#2c2c2e]">
              {filteredAlarms.map((a) => (
                <div
                  key={a.id}
                  onClick={() => setSelectedAlarm(a)}
                  className={`px-6 py-4 flex items-center justify-between cursor-pointer hover:bg-white/5 transition ${
                    selectedAlarm?.id === a.id ? 'bg-[#0a84ff]/5' : ''
                  }`}
                >
                  <div className="flex items-center space-x-4">
                    <span className={`h-2.5 w-2.5 rounded-full ${a.isGood ? 'bg-[#30d158]' : a.source === 'live' ? 'bg-[#ff9f0a]' : 'bg-[#0a84ff]'}`} />
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <p className="text-sm font-medium text-white">{a.description}</p>
                        <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${
                          a.isGood
                            ? 'bg-[#30d158]/15 text-[#30d158]'
                            : a.source === 'live'
                            ? 'bg-[#30d158]/15 text-[#30d158]'
                            : 'bg-[#0a84ff]/15 text-[#0a84ff]'
                        }`}>
                          {a.isGood ? '良品' : a.source === 'live' ? '实时检测' : '图片检测'}
                        </span>
                      </div>
                      <div className="flex space-x-3 text-xs text-[#8e8e93] font-mono">
                        <span className="flex items-center space-x-1">
                          <Calendar className="h-3 w-3 inline" />
                          <span>{new Date(a.timestamp).toLocaleDateString()}</span>
                        </span>
                        <span className="flex items-center space-x-1">
                          <Clock className="h-3 w-3 inline" />
                          <span>{new Date(a.timestamp).toLocaleTimeString()}</span>
                        </span>
                        <span>ID: #{resolveDefectClassId(a)}</span>
                        <span>批次: {a.batchId || '历史记录'}</span>
                        {a.itemName && <span>对象: {a.itemName}</span>}
                      </div>
                    </div>
                  </div>
                  <ArrowUpRight className="h-4 w-4 text-[#8e8e93]" />
                </div>
              ))}
              {filteredAlarms.length === 0 && (
                <div className="text-center py-20 text-[#8e8e93] select-none">
                  没有检测记录。
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="col-span-4 min-h-0 bg-[#1c1c1e] p-6 rounded-xl border border-[#2c2c2e] overflow-y-auto select-none">
        <h3 className="text-sm font-semibold mb-6 text-[#8e8e93] tracking-wider uppercase font-sans">
          记录详情
        </h3>

        {selectedAlarm ? (
          <div className="space-y-6">
            <div className="aspect-video bg-black rounded-lg border border-[#2c2c2e] relative flex items-center justify-center overflow-hidden">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(0,0,0,0)_0%,rgba(0,0,0,0.85)_100%)]" />
              <div className="text-center p-4 z-10">
                <span className="text-xs bg-[#ff9f0a] text-white px-2.5 py-1 rounded font-bold uppercase tracking-wider">
                  检测记录 (SNAPSHOT)
                </span>
                <p className="text-[10px] text-[#8e8e93] mt-2.5 font-mono">
                  TIMESTAMP: {selectedAlarm.timestamp}
                </p>
                <p className="text-[10px] text-[#0a84ff] font-mono">
                  TARGET: #{resolveDefectClassId(selectedAlarm)}
                </p>
              </div>
            </div>

            <div className="space-y-4 font-mono text-sm">
              <div className="flex justify-between py-2 border-b border-[#2c2c2e]">
                <span className="text-[#8e8e93]">事件类型:</span>
                <span className="font-bold text-[#ff9f0a] uppercase">{selectedAlarm.type}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-[#2c2c2e]">
                <span className="text-[#8e8e93]">检测批次:</span>
                <span className="font-bold text-white text-xs">{selectedAlarm.batchId || '历史记录'}</span>
              </div>
              <div className="flex justify-between py-2 border-b border-[#2c2c2e]">
                <span className="text-[#8e8e93]">目标编号:</span>
                <span className="font-bold text-white">#{resolveDefectClassId(selectedAlarm)}</span>
              </div>
              <div className="flex flex-col space-y-2 py-2">
                <span className="text-[#8e8e93]">描述:</span>
                <p className="text-xs text-white leading-relaxed bg-black/40 p-3 rounded-lg border border-[#2c2c2e]">
                  {selectedAlarm.description}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="text-center text-[#8e8e93] py-20">
            在左侧记录中点击查看详情。
          </div>
        )}

        <div className="mt-6 pt-5 border-t border-[#2c2c2e]">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-semibold text-white">缺陷类别编号说明</h4>
            <span className="text-[9px] text-[#8e8e93] font-mono">共 6 类（nc: 6）</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            {DEFECT_CLASS_DESCRIPTIONS.map((item) => (
              <div key={item.id} className="bg-black/30 border border-[#2c2c2e] rounded-lg px-2.5 py-2">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded bg-[#0a84ff]/20 text-[#0a84ff] flex items-center justify-center text-[10px] font-bold font-mono">
                    {item.id}
                  </span>
                  <span className="text-[11px] text-white font-semibold">{item.name}</span>
                </div>
                <p className="text-[9px] text-[#8e8e93] font-mono mt-1 truncate">{item.code}</p>
              </div>
            ))}
          </div>
          <p className="text-[9px] text-[#8e8e93] mt-3 leading-relaxed">
            图片检测记录中的 ID 对应上述缺陷类别编号；实时检测记录的 ID 可能是板端目标跟踪编号，应以缺陷描述为准。
          </p>
        </div>
      </div>
    </div>
  );
};
