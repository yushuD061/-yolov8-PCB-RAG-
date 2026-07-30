import { useState, useEffect, useCallback, useRef } from 'react';
import { TabId, SimulatedTarget, TelemetryMetrics, AlarmEvent, SystemConfig, getDefectNameCn } from './types';
import { WSClient } from './utils/wsClient';
import { normalizeTargets, normalizeTelemetry } from './utils/dataAdapter';
import { Header } from './components/Header';
import { Sidebar } from './components/Sidebar';
import { LiveDetectTab } from './components/LiveDetectTab';
import { ImageRecTab } from './components/ImageRecTab';
import { HistoryTab } from './components/HistoryTab';
import { ConfigTab } from './components/ConfigTab';
import { RagTab } from './components/RagTab';
import { UserTab } from './components/UserTab';
import { LoginScreen } from './components/LoginScreen';

let _fc = 0;  // 调试：视频帧计数器

export default function App() {
  const [currentUser, setCurrentUser] = useState<string | null>(() => {
    return sessionStorage.getItem('system_current_user');
  });
  const [activeTab, setActiveTab] = useState<TabId>('image_rec');
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isDarkMode, setIsDarkMode] = useState<boolean>(() => {
    const saved = localStorage.getItem('theme');
    return saved !== 'light';
  });

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.remove('light');
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      document.documentElement.classList.remove('dark');
      document.documentElement.classList.add('light');
      localStorage.setItem('theme', 'light');
    }
  }, [isDarkMode]);
  
  const [config, setConfig] = useState<SystemConfig>({
    selectedModel: 'yolo26n',
    localInference: false,
    saveResults: true,
    retentionDays: 30,
    jpegQuality: 85,
    maxFps: 30,
    npuMode: 'balanced',
    tempWarning: 75,
    reviewThreshold: 0.35,
    consecutiveAlerts: 5,
  });

  // 以后端持久化配置为准，避免刷新页面后恢复成前端默认值。
  useEffect(() => {
    fetch('/api/config')
      .then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        return resp.json();
      })
      .then((saved) => setConfig((prev) => ({ ...prev, ...saved })))
      .catch((err) => console.error('[Config] 加载后端配置失败:', err));
  }, []);

  const [targets, setTargets] = useState<SimulatedTarget[]>([]);
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);

  // 检测告警记录（持久化到 localStorage）
  const [alarms, setAlarms] = useState<AlarmEvent[]>(() => {
    try {
      const saved = localStorage.getItem('pcb_detection_history');
      const history: AlarmEvent[] = saved ? JSON.parse(saved) : [];
      // 回退到模型原始 class_id 0–5；仅反向迁移曾被改成 1–6 的记录。
      if (localStorage.getItem('pcb_history_id_base') === '1-6') {
        const migrated = history.map((record) => (
          record.source === 'image' && record.type === 'defect' &&
          record.targetId >= 1 && record.targetId <= 6
            ? { ...record, targetId: record.targetId - 1 }
            : record
        ));
        localStorage.setItem('pcb_history_id_base', '0-5');
        localStorage.setItem('pcb_detection_history', JSON.stringify(migrated));
        return migrated;
      }
      localStorage.setItem('pcb_history_id_base', '0-5');
      return history;
    } catch { return []; }
  });

  // 持久化到 localStorage
  useEffect(() => {
    localStorage.setItem('pcb_detection_history', JSON.stringify(alarms));
  }, [alarms]);

  // 终端日志
  const [logs, setLogs] = useState<string[]>([]);

  const pushLog = useCallback((message: string) => {
    setLogs((prev) => {
      const timestamp = new Date().toLocaleTimeString();
      const updated = [...prev, `[${timestamp}] ${message}`];
      return updated.slice(-50);
    });
  }, []);

  const [metrics, setMetrics] = useState<TelemetryMetrics>({
    fps: 0,
    npu: 0,
    cpu: 0,
    memUsed: 124,
    memTotal: 4096,
    temp: 34,
    latency: 0,
    selectedModel: 'yolo26n',
  });
  const [videoFrameUrl, setVideoFrameUrl] = useState<string | null>(null);

  // 实时检测去重：同一块板子的同一缺陷只记一次
  const dedupRef = useRef<{ sigs: Set<string>; lastTime: number }>({
    sigs: new Set(),
    lastTime: 0,
  });

  // 全局 WS 监听
  useEffect(() => {
    const ws = WSClient.getInstance();
    ws.connect();

    const unsubscribe = ws.subscribe((type, data) => {
      if (type === 'status_change') {
        setWsConnected(data.connected);
        if (data.connected) {
          pushLog('[SUCCESS] WebSocket 连接已建立，实时推理流在线。');
        } else {
          pushLog('[WARN] 连接断开，自动切换到客户端模拟模式。');
        }
      } else if (type === 'targets_stream') {
        const parsedTargets = normalizeTargets(data);
        setTargets(parsedTargets);
        // 去重记录：同一缺陷（同类型+同位置）只记一次；间隔 >5s 视为换板，重置
        if (Array.isArray(parsedTargets) && parsedTargets.length > 0) {
          const now = Date.now();
          const dedup = dedupRef.current;
          if (now - dedup.lastTime > 5000) {
            dedup.sigs.clear();  // 间隔超 5s，视为新板
          }
          dedup.lastTime = now;

          const newOnes: Array<{
            id: string; timestamp: string; type: string;
            targetId: number; source: 'live'; description: string;
          }> = [];
          for (const t of parsedTargets) {
            const sig = `${t.className}|${Math.round(t.x)}|${Math.round(t.y)}`;
            if (dedup.sigs.has(sig)) continue;
            dedup.sigs.add(sig);
            newOnes.push({
              id: `det-${now}-${t.id}-${Math.random().toString(36).slice(2, 6)}`,
              timestamp: new Date().toISOString(),
              type: 'defect',
              targetId: t.id,
              source: 'live',
              description: `检测到 ${getDefectNameCn(t.className)} 缺陷，置信度 ${(t.confidence * 100).toFixed(1)}%`,
            });
          }
          if (newOnes.length > 0) {
            setAlarms((prev) => [...newOnes, ...prev].slice(0, 200));
          }
        }
      } else if (type === 'telemetry_metrics') {
        const parsedMetrics = normalizeTelemetry(data);
        setMetrics({
          ...parsedMetrics,
          selectedModel: config.selectedModel,
        });
      } else if (type === 'log_broadcast') {
        if (data && data.message) {
          pushLog(data.message);
        }
      } else if (type === 'video_frame') {
        const url = URL.createObjectURL(data);
        setVideoFrameUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return url;
        });
        // 调试：每 50 帧打印一次
        _fc = (_fc || 0) + 1;
        if (_fc % 50 === 1) {
          console.log(`[video_frame] 收到第 ${_fc} 帧, blob size=${(data as Blob).size} bytes`);
        }
      }
    });

    return () => {
      unsubscribe();
    };
  }, [config.selectedModel, pushLog]);

  // 通过 WS 更新配置
  const updateConfig = (newCfg: Partial<SystemConfig>) => {
    setConfig((prev) => {
      const merged = { ...prev, ...newCfg };
      
      if (wsConnected) {
        const client = WSClient.getInstance();
        client.send('control_channel', 'CONF_UPDATE', merged);
      } else {
        pushLog(`[INFO] 本地配置已更新`);
      }

      fetch('/api/config', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newCfg),
      }).then((resp) => {
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      }).catch((err) => {
        pushLog(`[ERROR] 配置持久化失败: ${err?.message || String(err)}`);
      });

      return merged;
    });
  };

  const clearAlarms = () => {
    setAlarms([]);
    pushLog('[SUCCESS] 检测记录已清空。');
  };

  const handleLogout = () => {
    sessionStorage.removeItem('system_current_user');
    setCurrentUser(null);
    pushLog('[SUCCESS] 账户已安全退出。');
  };

  if (!currentUser) {
    return (
      <LoginScreen
        onLogin={(user) => {
          sessionStorage.setItem('system_current_user', user);
          setCurrentUser(user);
          pushLog(`[SUCCESS] 鉴权成功：欢迎 [${user}] 访问系统。`);
        }}
        isDarkMode={isDarkMode}
        setIsDarkMode={setIsDarkMode}
      />
    );
  }

  return (
    <div className={`flex flex-col h-screen overflow-hidden bg-[#121214] text-[#f5f5f7] ${isDarkMode ? 'dark' : 'light'}`}>
      <Header metrics={metrics} wsConnected={wsConnected} isDarkMode={isDarkMode} setIsDarkMode={setIsDarkMode} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />

        <main className="flex-1 flex flex-col overflow-hidden bg-[#121214]">
          <div className={activeTab === 'live_detect' ? '' : 'hidden'}>
            <LiveDetectTab
              targets={targets}
              selectedTargetId={selectedTargetId}
              setSelectedTargetId={setSelectedTargetId}
              pushLog={pushLog}
              videoFrameUrl={videoFrameUrl}
              wsConnected={wsConnected}
              metrics={{ fps: metrics.fps, npu: metrics.npu, temp: metrics.temp }}
            />
          </div>

          <div className={activeTab === 'image_rec' ? '' : 'hidden'}>
            <ImageRecTab pushLog={pushLog} onDetect={({ detections: dets, itemName, source, batchId }) => {
              if (!config.saveResults) {
                pushLog(`[统计] ${itemName}: 自动保存已关闭，本次结果不写入历史`);
                return;
              }
              setAlarms((prev) => {
                const defectRecords = dets.map((d, i) => ({
                  id: `img-${Date.now()}-${i}-${Math.random().toString(36).slice(2, 6)}`,
                  timestamp: new Date().toISOString(),
                  type: 'defect',
                  targetId: d.class_id,
                  source: 'image' as const,
                  batchId,
                  itemName,
                  isGood: false,
                  className: d.className,
                  description: `图片检测到 ${getDefectNameCn(d.className)} 缺陷，置信度 ${(d.confidence * 100).toFixed(1)}%`,
                }));
                const newOnes = defectRecords.length > 0 ? defectRecords : [{
                  id: `good-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
                  timestamp: new Date().toISOString(),
                  type: 'quality',
                  targetId: 0,
                  source: 'image' as const,
                  batchId,
                  itemName,
                  isGood: true,
                  description: `图片检测 ${itemName}：未发现缺陷（良品）`,
                }];
                return [...newOnes, ...prev].slice(0, 200);
              });
              fetch('/api/inspections/report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  detections: dets,
                  itemName,
                  source,
                  batchId,
                  timestamp: new Date().toISOString(),
                }),
              }).then(async (resp) => {
                const result = await resp.json();
                if (!resp.ok || !result.success) {
                  throw new Error(result.error || `HTTP ${resp.status}`);
                }
                pushLog(`[统计] ${itemName}: ${result.isGood ? '良品' : '不良品'}，已写入检测历史`);
              }).catch((err) => {
                pushLog(`[ERROR] 检测历史写入失败: ${err?.message || String(err)}`);
              });
            }} />
          </div>

          <div className={activeTab === 'history' ? 'flex-1 min-h-0 flex' : 'hidden'}>
            <HistoryTab alarms={alarms} clearAlarms={clearAlarms} />
          </div>

          <div className={activeTab === 'config' ? '' : 'hidden'}>
            <ConfigTab config={config} updateConfig={updateConfig} />
          </div>

          <div className={activeTab === 'rag' ? 'flex-1 min-h-0 flex' : 'hidden'}>
            <RagTab pushLog={pushLog} />
          </div>

          <div className={activeTab === 'user' ? '' : 'hidden'}>
            <UserTab logs={logs} currentUser={currentUser} onLogout={handleLogout} />
          </div>
        </main>
      </div>
    </div>
  );
}
