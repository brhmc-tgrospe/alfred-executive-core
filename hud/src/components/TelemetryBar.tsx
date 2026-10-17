import type { AlfredStatus, AudioDevice, LayoutMode } from "../types";
import {
  Cpu,
  HardDrive,
  Terminal,
  Eye,
  EyeOff,
  Disc,
  Mic,
  MicOff,
  MousePointerClick,
  Monitor,
  LayoutGrid,
  Gauge,
  Wifi,
  WifiOff,
} from "lucide-react";

interface TelemetryBarProps {
  status: AlfredStatus;
  cpu: number;
  ram: number;
  pingMs?: number;
  fps?: number;
  mouseX?: number;
  mouseY?: number;
  rmsVolume?: number;
  micLevel?: number;
  inputDevices?: AudioDevice[];
  currentDeviceId?: number | null;
  onSwitchInputDevice?: (deviceId: number) => void;
  activeTool: string | null;
  connected: boolean;
  micActive: boolean;
  clickThroughLocked?: boolean;
  layoutMode?: LayoutMode;
  stealthEnabled?: boolean;
  onToggleMic: () => void;
  onToggleClickThrough?: () => void;
  onToggleLayout?: () => void;
  onToggleStealth?: () => void;
  onInspectScreen?: () => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

const STATUS_BADGES: Record<
  AlfredStatus,
  { label: string; textClass: string; bgClass: string; borderClass: string; pulseClass: string }
> = {
  idle: {
    label: "STANDBY",
    textClass: "text-cyan-400",
    bgClass: "bg-cyan-500/10",
    borderClass: "border-cyan-500/30",
    pulseClass: "bg-cyan-400",
  },
  listening: {
    label: "LISTENING",
    textClass: "text-cyan-300",
    bgClass: "bg-cyan-500/20",
    borderClass: "border-cyan-400/50",
    pulseClass: "bg-cyan-300 animate-ping",
  },
  thinking: {
    label: "REASONING",
    textClass: "text-amber-400",
    bgClass: "bg-amber-500/15",
    borderClass: "border-amber-500/40",
    pulseClass: "bg-amber-400 animate-pulse",
  },
  speaking: {
    label: "EXECUTIVE VOCAL",
    textClass: "text-emerald-400",
    bgClass: "bg-emerald-500/15",
    borderClass: "border-emerald-500/40",
    pulseClass: "bg-emerald-400 animate-pulse",
  },
};

export function TelemetryBar({
  status,
  cpu,
  ram,
  pingMs = -1,
  fps = 60,
  mouseX = 0,
  mouseY = 0,
  rmsVolume = 0.0,
  micLevel,
  inputDevices = [],
  currentDeviceId = null,
  onSwitchInputDevice,
  activeTool,
  connected,
  micActive,
  clickThroughLocked = false,
  layoutMode = "cinema",
  stealthEnabled = true,
  onToggleMic,
  onToggleClickThrough,
  onToggleLayout,
  onToggleStealth,
  onInspectScreen,
  onMouseEnter,
  onMouseLeave,
}: TelemetryBarProps) {
  const badge = STATUS_BADGES[status] || STATUS_BADGES.idle;
  const currentMicLevel = micLevel ?? rmsVolume;
  const micPercent = Math.min(100, Math.max(0, Math.round(currentMicLevel * 100)));

  return (
    <header
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="hud-interactive w-full max-w-5xl mx-auto rounded-2xl bg-slate-950/85 backdrop-blur-xl border border-cyan-500/30 px-4 py-2 shadow-[0_8px_32px_rgba(0,0,0,0.6)] flex flex-col gap-1.5 text-xs select-none transition-all duration-200"
    >
      {/* Row 1: Brand, Status Badge, Active Tool (Left) | System Telemetry: CPU, RAM, PING, FPS (Right) */}
      <div className="w-full flex items-center justify-between gap-3">
        {/* Left: Brand, Status Badge, Active Tool */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex items-center gap-2 shrink-0">
            <div className="relative flex items-center justify-center">
              <Disc className="w-3.5 h-3.5 text-cyan-400 animate-spin" style={{ animationDuration: "12s" }} />
              <span
                className={`absolute w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-500 animate-ping"}`}
              />
            </div>
            <span className="font-mono tracking-widest text-xs font-bold bg-gradient-to-r from-cyan-300 via-sky-200 to-slate-200 bg-clip-text text-transparent">
              A.L.F.R.E.D.
            </span>
            <span className="text-[9px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-900/90 text-slate-400 border border-slate-800">
              CORE v1.0
            </span>
          </div>

          {/* Status Pill */}
          <div
            className={`flex items-center gap-1.5 px-2 py-0.5 rounded-full border ${badge.bgClass} ${badge.borderClass} ${badge.textClass} shrink-0`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${badge.pulseClass}`} />
            <span className="font-mono tracking-wider font-semibold text-[10px]">{badge.label}</span>
          </div>

          {/* Active Tool Pill */}
          {activeTool && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-[9px] animate-pulse truncate max-w-[200px]">
              <Terminal className="w-3 h-3 shrink-0 text-amber-400" />
              <span className="truncate">TOOL: {activeTool}</span>
            </div>
          )}
        </div>

        {/* Right: CPU, RAM, PING, FPS */}
        <div className="flex items-center gap-2.5 shrink-0">
          {/* CPU Meter */}
          <div className="flex items-center gap-1.5" title={`CPU Usage: ${cpu}%`}>
            <Cpu className="w-3 h-3 text-slate-400" />
            <div className="w-12">
              <div className="flex justify-between text-[9px] font-mono text-slate-400">
                <span>CPU</span>
                <span className={cpu > 80 ? "text-rose-400 font-bold" : "text-cyan-300"}>{cpu}%</span>
              </div>
              <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    cpu > 80 ? "bg-rose-500" : cpu > 50 ? "bg-amber-400" : "bg-cyan-400"
                  }`}
                  style={{ width: `${Math.min(cpu, 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* RAM Meter */}
          <div className="flex items-center gap-1.5" title={`RAM Usage: ${ram}%`}>
            <HardDrive className="w-3 h-3 text-slate-400" />
            <div className="w-12">
              <div className="flex justify-between text-[9px] font-mono text-slate-400">
                <span>RAM</span>
                <span className={ram > 85 ? "text-rose-400 font-bold" : "text-cyan-300"}>{ram}%</span>
              </div>
              <div className="h-1 w-full bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    ram > 85 ? "bg-rose-500" : ram > 65 ? "bg-amber-400" : "bg-sky-400"
                  }`}
                  style={{ width: `${Math.min(ram, 100)}%` }}
                />
              </div>
            </div>
          </div>

          {/* 8.8.8.8 Ping Latency */}
          <div
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-slate-900/80 border border-slate-700/60 font-mono text-[9px]"
            title={
              pingMs !== undefined && pingMs >= 0
                ? `TCP Socket Latency to 8.8.8.8: ${pingMs} ms`
                : "Network to 8.8.8.8 Offline or Unreachable"
            }
          >
            {pingMs !== undefined && pingMs >= 0 ? (
              <Wifi
                className={`w-3 h-3 ${
                  pingMs < 50 ? "text-emerald-400" : pingMs <= 150 ? "text-amber-400" : "text-rose-400"
                }`}
              />
            ) : (
              <WifiOff className="w-3 h-3 text-rose-500" />
            )}
            <span className="text-slate-400">PING</span>
            <span
              className={`font-bold ${
                pingMs !== undefined && pingMs >= 0
                  ? pingMs < 50
                    ? "text-emerald-300"
                    : pingMs <= 150
                    ? "text-amber-300"
                    : "text-rose-400"
                  : "text-rose-400"
              }`}
            >
              {pingMs !== undefined && pingMs >= 0 ? `${Math.round(pingMs)}ms` : "ERR"}
            </span>
          </div>

          {/* Real-time Render FPS */}
          <div
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-slate-900/80 border border-slate-700/60 font-mono text-[9px]"
            title={`Real-Time HUD Render Rate: ${fps} FPS`}
          >
            <Gauge
              className={`w-3 h-3 ${
                fps >= 55 ? "text-emerald-400" : fps >= 30 ? "text-amber-400" : "text-rose-400"
              }`}
            />
            <span className="text-slate-400">FPS</span>
            <span
              className={`font-bold ${
                fps >= 55 ? "text-emerald-300" : fps >= 30 ? "text-amber-300" : "text-rose-400"
              }`}
            >
              {fps}
            </span>
          </div>

          {/* Live Mouse Coordinates Pill */}
          <div
            className="flex items-center gap-1 px-1.5 py-0.5 rounded-lg bg-slate-900/80 border border-slate-700/60 font-mono text-[9px]"
            title={`Hardware OS Cursor Position: (${mouseX}, ${mouseY})`}
          >
            <MousePointerClick className="w-3 h-3 text-cyan-400" />
            <span className="text-slate-400">XY:</span>
            <span className="font-bold text-cyan-300">
              {mouseX}, {mouseY}
            </span>
          </div>
        </div>
      </div>

      {/* Row 2: All Controls Inline: MIC, LVL, Mic Device | CLICK-THROUGH, LAYOUT, STEALTH, INSPECT */}
      <div className="w-full flex items-center justify-between gap-2 border-t border-cyan-500/10 pt-1.5 overflow-x-auto scrollbar-none">
        {/* Left: Mic Button, Level Meter, Device Dropdown */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={onToggleMic}
            title={micActive ? "Mic Live (Click or Ctrl+Space to Mute)" : "Mic Muted (Click or Ctrl+Space to Talk)"}
            className={`flex items-center gap-1.5 px-2 py-1 rounded-lg font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
              micActive
                ? "bg-emerald-500/20 border-emerald-400/60 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.35)]"
                : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
            }`}
          >
            {micActive ? (
              <>
                <span className="relative flex h-1.5 w-1.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
                </span>
                <Mic className="w-3 h-3 text-emerald-400" />
                <span>MIC LIVE</span>
              </>
            ) : (
              <>
                <MicOff className="w-3 h-3 text-slate-500" />
                <span>MIC MUTED</span>
              </>
            )}
          </button>

          {/* Live Mic Input Level Meter */}
          {micActive && (
            <div
              className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-slate-900/80 border border-slate-700/60 text-slate-300"
              title={`Microphone Input Level: ${micPercent}%`}
            >
              <span className="font-mono text-[9px] text-slate-400">LVL</span>
              <div className="w-20 h-2.5 bg-slate-800/90 rounded-full overflow-hidden flex items-center p-0.5 border border-slate-700/50">
                <div
                  className={`h-full rounded-full transition-all duration-75 ${
                    currentMicLevel > 0.75
                      ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.8)]"
                      : currentMicLevel > 0.15
                      ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]"
                      : "bg-cyan-500/30"
                  }`}
                  style={{ width: `${Math.max(4, micPercent)}%` }}
                />
              </div>
              <span
                className={`font-mono text-[9px] font-bold min-w-[24px] text-right ${
                  currentMicLevel > 0.75
                    ? "text-amber-400"
                    : currentMicLevel > 0.15
                    ? "text-emerald-400"
                    : "text-slate-500"
                }`}
              >
                {micPercent}%
              </span>
            </div>
          )}

          {/* Microphone Device Dropdown Selector */}
          {inputDevices && inputDevices.length > 0 && (
            <div className="flex items-center" title="Select Microphone Hardware Device">
              <select
                value={currentDeviceId ?? (inputDevices.find((d) => d.is_default)?.id ?? inputDevices[0]?.id)}
                onChange={(e) => onSwitchInputDevice?.(Number(e.target.value))}
                className="bg-slate-900/90 hover:bg-slate-900 border border-slate-700/80 hover:border-cyan-500/40 text-cyan-200 font-mono text-[10px] rounded-lg px-2 py-1 outline-none cursor-pointer max-w-[180px] truncate transition-colors"
              >
                {inputDevices.map((dev) => (
                  <option key={dev.id} value={dev.id} className="bg-slate-950 text-slate-200">
                    {dev.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* Right: Click-Through, Layout, Stealth, Screen Inspect */}
        <div className="flex items-center gap-1.5 shrink-0">
          {/* Click-Through Interactivity Lock Button */}
          {onToggleClickThrough && (
            <button
              onClick={onToggleClickThrough}
              title={
                clickThroughLocked
                  ? "Click-Through is OFF (Interactivity is LOCKED ON). Click to enable desktop passthrough."
                  : "Click-Through is ON (Desktop passthrough active). Click to lock interactivity ON."
              }
              className={`flex items-center gap-1 px-2 py-1 rounded-lg font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
                clickThroughLocked
                  ? "bg-amber-500/20 border-amber-400/60 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.35)]"
                  : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
              }`}
            >
              <MousePointerClick className={`w-3 h-3 ${clickThroughLocked ? "text-amber-400" : "text-slate-400"}`} />
              <span>CLICK-THROUGH: {clickThroughLocked ? "OFF" : "ON"}</span>
            </button>
          )}

          {/* Layout Mode (Cinema vs Docked vs Orb-Only) Toggle */}
          {onToggleLayout && (
            <button
              onClick={onToggleLayout}
              title={`Layout Mode: ${layoutMode.toUpperCase()}. Click to cycle (Cinema -> Docked -> Orb-Only) or press Ctrl+Shift+A.`}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
                layoutMode === "docked"
                  ? "bg-cyan-500/20 border-cyan-400/60 text-cyan-300 shadow-[0_0_10px_rgba(6,182,212,0.3)]"
                  : layoutMode === "orb_only"
                  ? "bg-amber-500/20 border-amber-400/60 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.3)]"
                  : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
              }`}
            >
              {layoutMode === "docked" ? (
                <LayoutGrid className="w-3 h-3 text-cyan-400" />
              ) : layoutMode === "orb_only" ? (
                <Disc className="w-3 h-3 text-amber-400 animate-spin" />
              ) : (
                <Monitor className="w-3 h-3 text-slate-400" />
              )}
              <span>LAYOUT: {layoutMode.toUpperCase()}</span>
            </button>
          )}

          {/* Stealth Screen Inspection (setContentProtection) Toggle */}
          {onToggleStealth && (
            <button
              onClick={onToggleStealth}
              title={
                stealthEnabled
                  ? "Stealth Capture ON (HUD invisible to screen capture & Vision Cortex). Click to show HUD in screen captures."
                  : "Stealth Capture OFF (HUD visible in screen captures). Click to hide HUD from screen captures."
              }
              className={`flex items-center gap-1 px-2 py-1 rounded-lg font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
                stealthEnabled
                  ? "bg-cyan-500/20 border-cyan-400/60 text-cyan-300 shadow-[0_0_10px_rgba(6,182,212,0.3)]"
                  : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
              }`}
            >
              {stealthEnabled ? (
                <EyeOff className="w-3 h-3 text-cyan-400" />
              ) : (
                <Eye className="w-3 h-3 text-slate-400" />
              )}
              <span>STEALTH: {stealthEnabled ? "ON" : "OFF"}</span>
            </button>
          )}

          {/* Vision Inspect Trigger Button */}
          {onInspectScreen && (
            <button
              onClick={onInspectScreen}
              title="Inspect Active Screen"
              className="flex items-center gap-1 px-2 py-1 rounded-lg bg-cyan-950/60 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-500/30 hover:border-cyan-400 transition-colors font-mono text-[10px] font-bold cursor-pointer"
            >
              <Eye className="w-3 h-3 text-cyan-400" />
              <span>INSPECT</span>
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
