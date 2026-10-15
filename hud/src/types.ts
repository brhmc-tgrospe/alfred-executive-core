export type AlfredStatus = "idle" | "listening" | "thinking" | "speaking";

export interface PendingApproval {
  id: string;
  action: string;
  command: string;
  risk_level: string;
}

export interface AlfredStatePacket {
  type: "state";
  status: AlfredStatus;
  rms_volume: number;
  cpu: number;
  ram: number;
  transcript: string;
  active_tool: string | null;
  pending_approval: PendingApproval | null;
}

export interface ElectronAPI {
  setIgnoreMouseEvents: (ignore: boolean, options?: { forward: boolean }) => void;
  onPttTriggered?: (callback: () => void) => () => void;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
