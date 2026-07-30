import { WSRequest } from '../types';

export type WSMessageHandler = (type: string, data: any) => void;

export class WSClient {
  private static instance: WSClient | null = null;
  private socket: WebSocket | null = null;
  private handlers: Set<WSMessageHandler> = new Set();
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private isConnecting: boolean = false;
  private url: string = '';

  private constructor() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    // Standardize URL to point to the current location with /ws endpoint
    this.url = `${protocol}//${host}/ws`;
  }

  public static getInstance(): WSClient {
    if (!WSClient.instance) {
      WSClient.instance = new WSClient();
    }
    return WSClient.instance;
  }

  public connect(): void {
    if (this.socket || this.isConnecting) return;
    this.isConnecting = true;

    try {
      this.socket = new WebSocket(this.url);
      this.socket.binaryType = 'blob';

      this.socket.onopen = () => {
        this.isConnecting = false;
        console.log('[WS] Connected successfully');
        this.triggerHandlers('status_change', { connected: true });
      };

      this.socket.onmessage = (event) => {
        if (event.data instanceof Blob) {
          this.triggerHandlers('video_frame', event.data);
          return;
        }

        try {
          const message = JSON.parse(event.data);
          if (message.type) {
            this.triggerHandlers(message.type, message.data);
          } else if (message.channel) {
            this.triggerHandlers(message.channel, message);
          }
        } catch (e) {
          console.error('[WS] Error parsing JSON message', e);
        }
      };

      this.socket.onclose = () => {
        this.isConnecting = false;
        this.socket = null;
        console.log('[WS] Disconnected, scheduling reconnect...');
        this.triggerHandlers('status_change', { connected: false });
        this.scheduleReconnect();
      };

      this.socket.onerror = (err) => {
        console.error('[WS] Socket error', err);
        if (this.socket) {
          this.socket.close();
        }
      };
    } catch (e) {
      this.isConnecting = false;
      this.scheduleReconnect();
    }
  }

  public send(channel: string, method: string, data?: Record<string, unknown>): void {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      const req: WSRequest = {
        id: Math.random().toString(36).substring(2, 11),
        method,
        channel,
        data,
      };
      this.socket.send(JSON.stringify(req));
    } else {
      console.warn('[WS] Cannot send message, socket is not connected');
    }
  }

  public subscribe(handler: WSMessageHandler): () => void {
    this.handlers.add(handler);
    return () => {
      this.handlers.delete(handler);
    };
  }

  private triggerHandlers(type: string, data: any): void {
    this.handlers.forEach(handler => {
      try {
        handler(type, data);
      } catch (e) {
        console.error('[WS] Error calling message handler', e);
      }
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = setTimeout(() => {
      this.connect();
    }, 3000);
  }

  public get isConnected(): boolean {
    return this.socket !== null && this.socket.readyState === WebSocket.OPEN;
  }
}
