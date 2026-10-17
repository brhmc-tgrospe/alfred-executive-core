export type AlfredStatus = "idle" | "listening" | "thinking" | "speaking";
export type LayoutMode = "cinema" | "docked" | "orb_only";

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
  mic_level?: number;
  cpu: number;
  ram: number;
  ping_ms?: number;
  mouse_x?: number;
  mouse_y?: number;
  transcript: string;
  active_tool: string | null;
  pending_approval: PendingApproval | null;
  input_devices?: AudioDevice[];
  current_device_id?: number | null;
}

export interface ElectronAPI {
  setIgnoreMouseEvents: (ignore: boolean, options?: { forward: boolean }) => void;
  setContentProtection?: (enable: boolean) => void;
  onPttTriggered?: (callback: () => void) => () => void;
  onToggleLayoutMode?: (callback: () => void) => () => void;
  onSetLayoutMode?: (callback: (mode: LayoutMode) => void) => () => void;
  shutdownApp?: () => void;
  forceClickThrough?: () => void;
  onForceClickThrough?: (callback: () => void) => () => void;
}

declare global {
  interface Window {
    alfredElectron?: ElectronAPI;
    electronAPI?: ElectronAPI;
  }
}
