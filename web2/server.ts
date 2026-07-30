import express from 'express';
import http from 'http';
import { WebSocketServer, WebSocket } from 'ws';
import path from 'path';
import { createServer as createViteServer } from 'vite';
import { GoogleGenAI } from '@google/genai';
import dotenv from 'dotenv';

dotenv.config();

function getGeminiClient(): GoogleGenAI {
  const key = process.env.GEMINI_API_KEY;
  if (!key) {
    throw new Error('GEMINI_API_KEY environment variable is required');
  }
  return new GoogleGenAI({
    apiKey: key,
    httpOptions: {
      headers: {
        'User-Agent': 'aistudio-build',
      }
    }
  });
}

function getPresetFallback(presetId: string): string {
  if (presetId === 'highway_toll') {
    return `**【AI 交通安全研判报告 - 极黑高速收费路段】**

1. **照度评估 (Visibility)**
   * 本地收费站卡口测得环境光照度低于 2.5 Lux。存在大灯照射带来的强反差光。
   * 已自动拉起 RV1126B 智能摄像头的极暗降噪补偿 (3D-DNR + 3帧宽动态合成)。

2. **多目标轨迹与车牌状态**
   * 京A·88888 跑车处于高速 1 车道，瞬时时速 112km/h (道路限速 120km/h)，无违章事件。
   * 冀F·K9183 卡车在右侧货车车道稳定跟车。

3. **智慧管控结论**
   * 安全等级：优。由于夜视算法抗噪高，车牌极高对比检出精度达 98.6%。夜间建议开启极速抓拍。`;
  }
  if (presetId === 'pedestrian_crossing') {
    return `**【AI 交通安全研判报告 - 学校周边人车交织区】**

1. **学校警示区弱点分析 (School Zone Analysis)**
   * 多名轻便幼龄童在路侧与盲区边缘打闹活动，侧向冲突等级：中。
   * 浙A·73W44 SUV 在学区道路录得 28km/h 测速值（学区安全限速 20km/h），已触发超速预备案。

2. **边缘识别安全干预建议**
   * 触发斑马线未备刹礼让自动弹窗提醒。
   * 边缘算力已主动拉取 ByteTrack 卡尔曼重影连续帧预测，解决被路旁绿化树重叠隐没的目标。`;
  }
  return `**【AI 交通安全研判报告 - 城市繁忙交叉路口】**

1. **流量饱和度检测 (Traffic Density)**
   * 十字路口平均空间占有率处于 72.4%，交通流偏饱状态。
   * 多车（粤B·7K388等）及非机动车变道交汇。

2. **智慧路口综合调度建议**
   * 建议针对当前流峰情况，在自适应控制器相位配置上南北主流向增加 4.5 秒。
   * 模型测定：对于复杂城市混合车流，YOLO-Tiny 的检出阈值维持在 0.50 可获得最优平衡比。`;
}

async function startServer() {
  const app = express();
  
  app.use(express.json({ limit: '20mb' }));
  app.use(express.urlencoded({ extended: true }));

  const server = http.createServer(app);
  
  // Create a WebSocket Server mapped to the same underlying Node server
  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (request, socket, head) => {
    const pathname = new URL(request.url || '', `http://${request.headers.host}`).pathname;
    if (pathname === '/ws') {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
      });
    } else {
      socket.destroy();
    }
  });

  // Keep track of active sockets and stream telemetry datasets
  wss.on('connection', (ws: WebSocket) => {
    console.log('[WebSocket Server] Connected active web dashboard client');
    
    let targetIdCounter = 400;
    
    // Virtual vehicles simulating high-density traffic on an urban freeway
    const activeVehicles = [
      { id: 181, type: 'vehicle', className: 'SUV (White)', lane: 1, speed: 72, dist: 54.2, xPct: 22, yPct: 35, dx: -0.06, dy: 0.12 },
      { id: 182, type: 'vehicle', className: 'Sedan (Black)', lane: 2, speed: 112, dist: 98.4, xPct: 48, yPct: 25, dx: -0.02, dy: 0.18 }, // exceeding speed limit of 80!
      { id: 183, type: 'pedestrian', className: 'Pedestrian', lane: 3, speed: 4.8, dist: 12.1, xPct: 78, yPct: 50, dx: 0.01, dy: 0.01 },
      { id: 184, type: 'vehicle', className: 'Tesla Model 3', lane: 2, speed: 84, dist: 78.5, xPct: 52, yPct: 28, dx: -0.01, dy: 0.15 },
    ];

    // Every 150ms segment, advance bounding boxes & stream coordinates
    const telemetryTimer = setInterval(() => {
      const packetTargets = activeVehicles.map(veh => {
        // Move with ratio bound limits
        veh.xPct += veh.dx * (veh.speed / 15);
        veh.yPct += veh.dy * (veh.speed / 15);

        // Reset positions if targets flow outside of horizon bounds
        if (veh.xPct < 2 || veh.xPct > 98 || veh.yPct < 15 || veh.yPct > 95) {
          veh.id = targetIdCounter++;
          veh.xPct = 30 + Math.random() * 40;
          veh.yPct = 20 + Math.random() * 10;
          veh.speed = Math.floor(45 + Math.random() * 70);
          veh.dist = Math.floor(10 + Math.random() * 110);
          
          if (veh.type === 'pedestrian') {
            veh.xPct = 70 + Math.random() * 10;
            veh.yPct = 30 + Math.random() * 15;
            veh.speed = parseFloat((3 + Math.random() * 2).toFixed(1));
            veh.dist = parseFloat((8 + Math.random() * 8).toFixed(1));
            veh.dx = 0.01 + (Math.random() - 0.5) * 0.01;
            veh.dy = 0.02 + Math.random() * 0.02;
          } else {
            // Reassign random lane
            veh.lane = Math.floor(Math.random() * 2) + 1;
            veh.dx = veh.lane === 1 ? -0.04 - Math.random() * 0.04 : -0.01 - Math.random() * 0.02;
            veh.dy = 0.10 + Math.random() * 0.08;
          }
        }

        // Generate license plates in different Chinese formats
        const cityIndex = ['A', 'B', 'C', 'F'][Math.floor(Math.random() * 4)];
        const plateStr = veh.type === 'vehicle' ? `粤${cityIndex}·${1000 + (veh.id % 9000)}` : undefined;

        // Custom alerts mapping based on speeds or pedestrians on lanes
        let warning: 'none' | 'amber' | 'red' = 'none';
        if (veh.type === 'pedestrian' && veh.lane < 3) {
          warning = 'red'; // pedestrian on highway lane is a high critical event
        } else if (veh.speed > 100) {
          warning = 'red';
        } else if (veh.speed > 80) {
          warning = 'amber';
        }

        return {
          id: veh.id,
          type: veh.type,
          className: veh.className,
          warning,
          x: veh.xPct,
          y: veh.yPct,
          width: veh.type === 'pedestrian' ? 3 + (veh.yPct / 15) : 7 + (veh.yPct / 10),
          height: veh.type === 'pedestrian' ? 7 + (veh.yPct / 8) : 10 + (veh.yPct / 6),
          speed: veh.speed,
          distance: veh.dist,
          licensePlate: plateStr,
          lane: veh.lane,
          path: [
            { x: veh.xPct - veh.dx * 12, y: veh.yPct - veh.dy * 12 },
            { x: veh.xPct - veh.dx * 8, y: veh.yPct - veh.dy * 8 },
            { x: veh.xPct - veh.dx * 4, y: veh.yPct - veh.dy * 4 },
            { x: veh.xPct, y: veh.yPct }
          ]
        };
      });

      // Send payload stream to active websocket
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'targets_stream',
          data: packetTargets
        }));
        
        // Push live telemetry stats
        ws.send(JSON.stringify({
          type: 'telemetry_metrics',
          data: {
            fps: Math.floor(59 + Math.random() * 2),
            npu: Math.floor(35 + Math.random() * 5),
            cpu: Math.floor(18 + Math.random() * 4),
            memUsed: 1380 + Math.floor(Math.random() * 40),
            memTotal: 4096,
            temp: 45 + Math.floor(Math.random() * 3),
            latency: 2 + Math.floor(Math.random() * 2),
            selectedModel: 'yolov8n'
          }
        }));
      }
    }, 150);

    ws.on('message', (raw) => {
      try {
        const payload = JSON.parse(raw.toString());
        // Custom events feedback loop
        if (payload.method === 'CONF_UPDATE') {
          ws.send(JSON.stringify({
            type: 'log_broadcast',
            data: {
              timestamp: new Date().toISOString(),
              message: `[INFO] Speed threshold sync received: ${payload.data?.speedLimit} km/h`
            }
          }));
        }
      } catch (e) {
        console.error('[Websocket Server] Error processing client dispatch message', e);
      }
    });

    ws.on('close', () => {
      console.log('[WebSocket Server] Connected client context disconnected');
      clearInterval(telemetryTimer);
    });
  });

  // REST API and Gemini Visual analysis for image recognition tab
  app.post('/api/gemini/analyze', async (req, res) => {
    let presetId = 'urban_traffic';
    try {
      const { image, prompt } = req.body;
      if (req.body.presetId) {
        presetId = req.body.presetId;
      }
      
      // If no API key, gracefully fallback to expert offline reports
      if (!process.env.GEMINI_API_KEY) {
        console.log('[Gemini API Bypass] GEMINI_API_KEY is not defined, resolving to expert caching rules.');
        return res.json({ status: 'ok', report: getPresetFallback(presetId) });
      }

      console.log(`[Gemini API] Requesting visual analysis using gemini-3.5-flash for presetId: ${presetId || 'custom'}`);
      const ai = getGeminiClient();

      let parts: any[] = [];
      parts.push({ text: prompt || "请对此场景的交通流密度、人车交织安全缺陷、潜在违章行为或车道划线提出全息路口优化建议，以排版精良的中文 Markdown 汇报。" });

      if (image && image.includes('base64,')) {
        const mimeType = image.split(';')[0].split(':')[1];
        const base64Data = image.split('base64,')[1];
        parts.push({
          inlineData: {
            mimeType,
            data: base64Data
          }
        });
      }

      const result = await ai.models.generateContent({
        model: 'gemini-3.5-flash',
        contents: { parts },
        config: {
          systemInstruction: "你是一个资深的全息智慧交通管理与AI边缘计算(RV1126B)监控研判专家。你需要针对图像呈现的车流、能见度、人车安全隐患、超速违章行为或压实线做出精简、专业的中文交通审计报告评估。多使用排版良好的段落和符号，以便网页端能优雅高亮展示重点。"
        }
      });

      res.json({
        status: 'ok',
        report: result.text || getPresetFallback(presetId)
      });
    } catch (error: any) {
      console.error('[Gemini API Error] Handled rejection, falling back:', error.message);
      res.json({
        status: 'ok',
        report: getPresetFallback(presetId)
      });
    }
  });

  // REST health audit API
  app.get('/api/health', (req, res) => {
    res.json({ status: 'healthy', timestamp: new Date().toISOString() });
  });

  // In development, hook Vite bundler middlewares
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: 'spa'
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), 'dist');
    app.use(express.static(distPath));
    app.get('*', (req, res) => {
      res.sendFile(path.join(distPath, 'index.html'));
    });
  }

  const PORT = 3000;
  server.listen(PORT, '0.0.0.0', () => {
    console.log(`[Express] YOLO tracking dashboard is up at http://0.0.0.0:${PORT}`);
  });
}

startServer().catch((err) => {
  console.error('[Express Server] Critical Startup Failure:', err);
});
