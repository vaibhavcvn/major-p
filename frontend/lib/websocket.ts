import { getAuthToken } from "./auth";

const WS_BASE_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export class RealtimeClient {
  private socket: WebSocket | null = null;
  private url: string;
  private onMessageCallback: (data: any) => void;
  private onConnectCallback?: () => void;
  private onDisconnectCallback?: () => void;
  private reconnectTimer: any = null;

  constructor(
    channelPath: string,
    onMessage: (data: any) => void,
    onConnect?: () => void,
    onDisconnect?: () => void
  ) {
    // Append the JWT as a query param — the only way to auth a browser WebSocket.
    // The backend verifies this token before accepting the connection.
    const token = getAuthToken();
    const separator = channelPath.includes("?") ? "&" : "?";
    const authenticatedPath = token
      ? `${channelPath}${separator}token=${encodeURIComponent(token)}`
      : channelPath;

    this.url = `${WS_BASE_URL}${authenticatedPath}`;
    this.onMessageCallback = onMessage;
    this.onConnectCallback = onConnect;
    this.onDisconnectCallback = onDisconnect;
  }

  public connect() {
    try {
      this.socket = new WebSocket(this.url);

      this.socket.onopen = () => {
        console.log(`[WebSocket Connected] -> ${this.url.split("?")[0]}`); // don't log the token
        if (this.onConnectCallback) this.onConnectCallback();
        if (this.reconnectTimer) {
          clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
      };

      this.socket.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          this.onMessageCallback(parsed);
        } catch (err) {
          console.error("Error parsing WebSocket payload:", err);
        }
      };

      this.socket.onclose = (evt) => {
        const wasAuthError = evt.code === 4001 || evt.code === 4003;
        if (wasAuthError) {
          console.error(`[WebSocket Auth Rejected] code=${evt.code} reason=${evt.reason}`);
          if (this.onDisconnectCallback) this.onDisconnectCallback();
          // Do not reconnect on auth errors — token is invalid or wrong channel
          return;
        }
        console.warn(`[WebSocket Disconnected] -> ${this.url.split("?")[0]}. Retrying in 3s...`);
        if (this.onDisconnectCallback) this.onDisconnectCallback();
        this.scheduleReconnect();
      };

      this.socket.onerror = (error) => {
        console.error("[WebSocket Error]:", error);
      };
    } catch (e) {
      console.error("WebSocket connection failure:", e);
      this.scheduleReconnect();
    }
  }

  private scheduleReconnect() {
    if (!this.reconnectTimer) {
      this.reconnectTimer = setTimeout(() => {
        this.connect();
      }, 3000);
    }
  }

  public disconnect() {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }
}
