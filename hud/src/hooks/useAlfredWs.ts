import { useEffect, useState, useRef, useCallback } from "react";
import type { AlfredStatePacket } from "../types";

const DEFAULT_STATE: AlfredStatePacket = {
  type: "state",
  status: "idle",
  rms_volume: 0.0,
  cpu: 0.0,
  ram: 0.0,
  transcript: "A.L.F.R.E.D. Core Online. Telemetry standing by, Sir.",
  active_tool: null,
  pending_approval: null,
};

export function useAlfredWs(url: string = "ws://127.0.0.1:8765/hud") {
  const [state, setState] = useState<AlfredStatePacket>(DEFAULT_STATE);
  const [connected, setConnected] = useState<boolean>(false);
  const wsRef = useRef<WebSocket | null>(null);
  const connectFnRef = useRef<() => void>(() => {});
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        setConnected(true);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data && data.type === "state") {
            setState(data as AlfredStatePacket);
          }
        } catch {
          // Ignore parse errors
        }
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        // Reconnect after 2 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connectFnRef.current();
        }, 2000);
      };

      ws.onerror = () => {
        ws.close();
      };
    } catch {
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connectFnRef.current();
      }, 2000);
    }
  }, [url]);

  useEffect(() => {
    connectFnRef.current = connect;
  }, [connect]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendApproval = useCallback((id: string, approved: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "approval_response", id, approved }));
    }
    // Optimistically clear approval in local state
    setState((prev) => ({ ...prev, pending_approval: null }));
  }, []);

  const sendPtt = useCallback((down: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ptt_event", state: down ? "down" : "up" }));
    }
  }, []);

  const sendInspectScreen = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "inspect_screen_trigger" }));
    }
  }, []);

  // Method to inject mock state for browser verification without live backend
  const injectMockState = useCallback((partial: Partial<AlfredStatePacket>) => {
    setState((prev) => ({ ...prev, ...partial }));
  }, []);

  return {
    state,
    connected,
    sendApproval,
    sendPtt,
    sendInspectScreen,
    injectMockState,
  };
}
