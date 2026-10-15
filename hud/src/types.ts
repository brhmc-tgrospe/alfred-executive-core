export type AlfredStatus = "idle" | "listening" | "thinking" | "speaking";

export interface PendingApproval {
  id: string;
  action: string;
  command: string;
  risk_level: string;
}

export interface AudioDevice {
  id: number;
  name: string;
  channels: number;
  is_default?: boolean;
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
  input_devices?: AudioDevice[];
  current_device_id?: number | null;
}

export interface ElectronAPI {
  setIgnoreMouseEvents: (ignore: boolean, options?: { forward: boolean }) => void;
  onPttTriggered?: (callback: () => void) => () => void;
}

declare global {
  interface Window {
    alfredElectron?: ElectronAPI;
    electronAPI?: ElectronAPI;
  }
}
