import type { AlfredStatus, AudioDevice } from "../types";
import { Cpu, HardDrive, Terminal, Eye, Disc, Mic, MicOff, MousePointerClick } from "lucide-react";

interface TelemetryBarProps {
  status: AlfredStatus;
  cpu: number;
  ram: number;
  rmsVolume?: number;
  inputDevices?: AudioDevice[];
  currentDeviceId?: number | null;
  onSwitchInputDevice?: (deviceId: number) => void;
  activeTool: string | null;
  connected: boolean;
  micActive: boolean;
  clickThroughLocked?: boolean;
  onToggleMic: () => void;
  onToggleClickThrough?: () => void;
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
  rmsVolume = 0.0,
  inputDevices = [],
  currentDeviceId = null,
  onSwitchInputDevice,
  activeTool,
  connected,
  micActive,
  clickThroughLocked = false,
  onToggleMic,
  onToggleClickThrough,
  onInspectScreen,
  onMouseEnter,
  onMouseLeave,
}: TelemetryBarProps) {
  const badge = STATUS_BADGES[status] || STATUS_BADGES.idle;

  return (
    <header
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="w-full max-w-5xl mx-auto rounded-2xl bg-slate-950/85 backdrop-blur-xl border border-cyan-500/30 px-5 py-3 shadow-[0_8px_32px_rgba(0,0,0,0.6)] flex items-center justify-between gap-3 text-xs select-none transition-all duration-200"
    >
      {/* Brand & Connection Status */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="relative flex items-center justify-center">
            <Disc className="w-4 h-4 text-cyan-400 animate-spin" style={{ animationDuration: "12s" }} />
            <span
              className={`absolute w-1.5 h-1.5 rounded-full ${connected ? "bg-emerald-400" : "bg-rose-500 animate-ping"}`}
            />
          </div>
          <span className="font-mono tracking-widest text-sm font-bold bg-gradient-to-r from-cyan-300 via-sky-200 to-slate-200 bg-clip-text text-transparent">
            A.L.F.R.E.D.
          </span>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-900/90 text-slate-400 border border-slate-800">
            CORE v1.0
          </span>
        </div>

        {/* Status Pill */}
        <div
          className={`flex items-center gap-2 px-2.5 py-1 rounded-full border ${badge.bgClass} ${badge.borderClass} ${badge.textClass}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${badge.pulseClass}`} />
          <span className="font-mono tracking-wider font-semibold text-[11px]">{badge.label}</span>
        </div>
      </div>

      {/* Middle: Active Tool, Mic Toggle, Mic Level Meter, Device Selector & Click-Through Lock */}
      <div className="flex-1 flex items-center justify-center min-w-0 px-2 gap-2 flex-wrap">
        {activeTool && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300 font-mono text-[10px] animate-pulse truncate max-w-xs">
            <Terminal className="w-3 h-3 shrink-0 text-amber-400" />
            <span className="truncate">TOOL: {activeTool}</span>
          </div>
        )}

        {/* Toggle-to-Talk Switch */}
        <button
          onClick={onToggleMic}
          title={micActive ? "Mic Live (Click or Ctrl+Space to Mute)" : "Mic Muted (Click or Ctrl+Space to Talk)"}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
            micActive
              ? "bg-emerald-500/20 border-emerald-400/60 text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.35)]"
              : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
          }`}
        >
          {micActive ? (
            <>
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <Mic className="w-3.5 h-3.5 text-emerald-400" />
              <span>MIC LIVE</span>
            </>
          ) : (
            <>
              <MicOff className="w-3.5 h-3.5 text-slate-500" />
              <span>MIC MUTED</span>
            </>
          )}
        </button>

        {/* Live Mic Input Level Meter */}
        {micActive && (
          <div
            className="flex items-center gap-1.5 px-2 py-1 rounded-xl bg-slate-900/80 border border-slate-700/60 text-slate-300"
            title={`Microphone Input Level: ${(rmsVolume * 100).toFixed(0)}%`}
          >
            <span className="font-mono text-[9px] text-slate-400 hidden sm:inline">LVL</span>
            <div className="w-12 h-1.5 bg-slate-800 rounded-full overflow-hidden flex items-center p-0.5">
              <div
                className={`h-full rounded-full transition-all duration-75 ${
                  rmsVolume > 0.6
                    ? "bg-amber-400 shadow-[0_0_8px_rgba(251,191,36,0.6)]"
                    : rmsVolume > 0.04
                    ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]"
                    : "bg-cyan-500/30"
                }`}
                style={{ width: `${Math.min(100, Math.max(8, rmsVolume * 100))}%` }}
              />
            </div>
          </div>
        )}

        {/* Microphone Device Dropdown Selector */}
        {inputDevices && inputDevices.length > 0 && (
          <div className="flex items-center" title="Select Microphone Hardware Device">
            <select
              value={currentDeviceId ?? (inputDevices.find((d) => d.is_default)?.id ?? inputDevices[0]?.id)}
              onChange={(e) => onSwitchInputDevice?.(Number(e.target.value))}
              className="bg-slate-900/90 hover:bg-slate-900 border border-slate-700/80 hover:border-cyan-500/40 text-cyan-200 font-mono text-[10px] rounded-xl px-2 py-1 outline-none cursor-pointer max-w-[130px] sm:max-w-[155px] truncate transition-colors"
            >
              {inputDevices.map((dev) => (
                <option key={dev.id} value={dev.id} className="bg-slate-950 text-slate-200">
                  {dev.name.length > 22 ? dev.name.slice(0, 20) + "..." : dev.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Click-Through Interactivity Lock Button */}
        {onToggleClickThrough && (
          <button
            onClick={onToggleClickThrough}
            title={
              clickThroughLocked
                ? "Click-Through is OFF (Interactivity is LOCKED ON). Click to enable desktop passthrough."
                : "Click-Through is ON (Desktop passthrough active). Click to lock interactivity ON."
            }
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl font-mono text-[10px] font-bold transition-all duration-200 cursor-pointer border ${
              clickThroughLocked
                ? "bg-amber-500/20 border-amber-400/60 text-amber-300 shadow-[0_0_15px_rgba(245,158,11,0.35)]"
                : "bg-slate-900/80 border-slate-700/60 text-slate-400 hover:text-cyan-300 hover:border-cyan-500/40"
            }`}
          >
            <MousePointerClick className={`w-3 h-3 ${clickThroughLocked ? "text-amber-400" : "text-slate-400"}`} />
            <span>CLICK-THROUGH: {clickThroughLocked ? "OFF" : "ON"}</span>
          </button>
        )}
      </div>

      {/* Right Side: System Telemetry & Screen Inspect */}
      <div className="flex items-center gap-4">
        {/* CPU Meter */}
        <div className="flex items-center gap-2">
          <Cpu className="w-3.5 h-3.5 text-slate-400" />
          <div className="w-16">
            <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-0.5">
              <span>CPU</span>
              <span className={cpu > 80 ? "text-rose-400 font-bold" : "text-cyan-300"}>{cpu}%</span>
            </div>
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
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
        <div className="flex items-center gap-2">
          <HardDrive className="w-3.5 h-3.5 text-slate-400" />
          <div className="w-16">
            <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-0.5">
              <span>RAM</span>
              <span className={ram > 85 ? "text-rose-400 font-bold" : "text-cyan-300"}>{ram}%</span>
            </div>
            <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
              <div
                className={`h-full transition-all duration-300 ${
                  ram > 85 ? "bg-rose-500" : ram > 65 ? "bg-amber-400" : "bg-sky-400"
                }`}
                style={{ width: `${Math.min(ram, 100)}%` }}
              />
            </div>
          </div>
        </div>

        {/* Vision Inspect Trigger Button */}
        {onInspectScreen && (
          <button
            onClick={onInspectScreen}
            title="Inspect Active Screen"
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-cyan-950/60 hover:bg-cyan-900/80 text-cyan-300 border border-cyan-500/30 hover:border-cyan-400 transition-colors font-mono text-[10px] cursor-pointer"
          >
            <Eye className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">INSPECT</span>
          </button>
        )}
      </div>
    </header>
  );
}
