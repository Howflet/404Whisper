// WebSocket client with auto-reconnect

import type { WSEvent } from '../types';

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimeout: number | null = null;
  private listeners: ((event: WSEvent) => void)[] = [];

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return;

    this.ws = new WebSocket('ws://localhost:8001/ws');

    this.ws.onopen = () => {
      console.log('WebSocket connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const wsEvent: WSEvent = JSON.parse(event.data);
        this.listeners.forEach(listener => listener(wsEvent));
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...');
      this.reconnectTimeout = window.setTimeout(() => this.connect(), 1000);
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  disconnect() {
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  onMessage(listener: (event: WSEvent) => void) {
    this.listeners.push(listener);
    return () => {
      this.listeners = this.listeners.filter(l => l !== listener);
    };
  }
}

export const wsClient = new WebSocketClient();