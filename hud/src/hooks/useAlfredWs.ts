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
  const lastStateRef = useRef<AlfredStatePacket>(DEFAULT_STATE);
  const lastAudioThrottleRef = useRef<number>(0);

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
            const packet = data as AlfredStatePacket;
            const last = lastStateRef.current;

            // Only trigger full React re-render when primary operational telemetry changes
            const primaryChanged =
              last.status !== packet.status ||
              last.transcript !== packet.transcript ||
              last.active_tool !== packet.active_tool ||
              last.cpu !== packet.cpu ||
              last.ram !== packet.ram ||
              last.ping_ms !== packet.ping_ms ||
              last.current_device_id !== packet.current_device_id ||
              JSON.stringify(last.pending_approval) !== JSON.stringify(packet.pending_approval) ||
              last.input_devices?.length !== packet.input_devices?.length;

            const now = Date.now();
            if (primaryChanged) {
              lastAudioThrottleRef.current = now;
              lastStateRef.current = packet;
              setState(packet);
            } else {
              // High-frequency rms_volume and mic_level updates throttled to 10Hz (every 100ms)
              if (now - lastAudioThrottleRef.current >= 100) {
                const rmsDiff = Math.abs((last.rms_volume ?? 0) - (packet.rms_volume ?? 0));
                const micDiff = Math.abs((last.mic_level ?? 0) - (packet.mic_level ?? 0));
                if (rmsDiff > 0.01 || micDiff > 0.01) {
                  lastAudioThrottleRef.current = now;
                  lastStateRef.current = {
                    ...lastStateRef.current,
                    rms_volume: packet.rms_volume,
                    mic_level: packet.mic_level,
                  };
                  setState((prev) => ({
                    ...prev,
                    rms_volume: packet.rms_volume,
                    mic_level: packet.mic_level,
                  }));
                }
              }
            }
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

  const [micActive, setMicActive] = useState<boolean>(true);

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

  const switchInputDevice = useCallback((deviceId: number) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "set_input_device", device_id: deviceId }));
    }
    setState((prev) => ({ ...prev, current_device_id: deviceId }));
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
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "simulate_pulse", intensity }));
    }
    // Optimistically elevate locally for instant zero-latency feedback
    setState((prev) => ({ ...prev, rms_volume: intensity, status: "speaking" }));
  }, []);

  const simulateApproval = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "simulate_approval" }));
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
    micActive,
    toggleMic,
    switchInputDevice,
    sendApproval,
    sendPtt,
    sendTextPrompt,
    pulseRms,
    simulateApproval,
    sendInspectScreen,
    injectMockState,
  };
}
