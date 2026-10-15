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

  const [micActive, setMicActive] = useState<boolean>(false);

  const sendApproval = useCallback((id: string, approved: boolean) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "approval_response", id, approved }));
    }
    // Optimistically clear approval in local state
    setState((prev) => ({ ...prev, pending_approval: null }));
  }, []);

  const sendPtt = useCallback((down: boolean) => {
    setMicActive(down);
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "ptt_event", state: down ? "down" : "up" }));
    }
  }, []);

  const toggleMic = useCallback(() => {
    setMicActive((prev) => {
      const next = !prev;
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ptt_event", state: next ? "down" : "up" }));
      }
      return next;
    });
  }, []);

  const sendTextPrompt = useCallback((text: string) => {
    if (!text.trim()) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "text_prompt", text: text.trim() }));
    }
    // Optimistically append directive to transcript for immediate feedback
    setState((prev) => ({
      ...prev,
      transcript: `${prev.transcript}\n› Directive: ${text.trim()}`,
      status: prev.status === "idle" ? "thinking" : prev.status,
    }));
  }, []);

  const pulseRms = useCallback((intensity = 0.85) => {
    setState((prev) => ({ ...prev, rms_volume: intensity }));
    let decayVal = intensity;
    const interval = setInterval(() => {
      decayVal *= 0.7;
      if (decayVal < 0.02) {
        decayVal = 0.0;
        clearInterval(interval);
      }
      setState((prev) => ({ ...prev, rms_volume: Number(decayVal.toFixed(3)) }));
    }, 40);
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
    micActive,
    toggleMic,
    sendApproval,
    sendPtt,
    sendTextPrompt,
    pulseRms,
    sendInspectScreen,
    injectMockState,
  };
}
