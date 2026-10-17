import { useEffect, useState } from "react";
import type { PendingApproval } from "../types";
import { AlertTriangle, ShieldAlert, CheckCircle2, XCircle, Clock } from "lucide-react";

interface ApprovalModalProps {
  approval: PendingApproval;
  onRespond: (id: string, approved: boolean) => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export function ApprovalModal({
  approval,
  onRespond,
  onMouseEnter,
  onMouseLeave,
}: ApprovalModalProps) {
  const [timeLeft, setTimeLeft] = useState<number>(30);

  // 30-Second Security Timeout Visual Timer
  useEffect(() => {
    const interval = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          onRespond(approval.id, false); // Auto-abort upon timeout
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [approval.id, onRespond]);

  // Keyboard Event Listeners: Enter -> Authorize, Escape -> Abort
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        onRespond(approval.id, true);
      } else if (e.key === "Escape") {
        e.preventDefault();
        onRespond(approval.id, false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [approval.id, onRespond]);

  const percentage = (timeLeft / 30) * 100;

  return (
    <div
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="hud-interactive fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
    >
      <div className="w-full max-w-lg rounded-2xl bg-slate-950/95 backdrop-blur-2xl border-2 border-amber-500/80 shadow-[0_0_50px_rgba(245,158,11,0.35)] overflow-hidden">
        {/* Top Warning Banner */}
        <div className="bg-gradient-to-r from-amber-600/30 via-red-600/30 to-amber-600/30 px-6 py-4 border-b border-amber-500/40 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-amber-500/20 border border-amber-400/40 text-amber-300 animate-pulse">
              <ShieldAlert className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-sm font-bold font-mono tracking-widest text-amber-200">
                EXECUTIVE SECURITY CLEARANCE
              </h2>
              <p className="text-[11px] font-mono text-amber-300/80">
                High-Risk OS Command Execution Request
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-red-500/20 border border-red-500/40 text-red-300 font-mono text-xs font-bold">
            <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
            <span>{approval.risk_level.toUpperCase()} RISK</span>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-4">
          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px] font-mono text-slate-400">
              <span>TARGET ACTION:</span>
              <span className="text-slate-300 font-bold">{approval.action}</span>
            </div>
            <div className="flex justify-between text-[11px] font-mono text-slate-400">
              <span>REQUEST ID:</span>
              <span className="text-amber-400/90 font-mono">{approval.id}</span>
            </div>
          </div>

          {/* Terminal Command Preview */}
          <div className="space-y-1.5">
            <span className="text-[11px] font-mono text-slate-400">COMMAND PAYLOAD:</span>
            <div className="p-3.5 rounded-xl bg-slate-900 border border-slate-800 font-mono text-xs text-rose-300 font-medium break-all select-all">
              <span className="text-slate-500 select-none">$ </span>
              {approval.command}
            </div>
          </div>

          {/* Countdown Timer */}
          <div className="space-y-1 pt-1">
            <div className="flex items-center justify-between text-[11px] font-mono text-slate-400">
              <span className="flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                Auto-abort timeout in:
              </span>
              <span className="text-amber-300 font-bold">{timeLeft}s</span>
            </div>
            <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-slate-800">
              <div
                className="h-full bg-gradient-to-r from-amber-400 to-rose-500 transition-all duration-1000 ease-linear"
                style={{ width: `${percentage}%` }}
              />
            </div>
          </div>
        </div>

        {/* Actions Footer */}
        <div className="px-6 py-4 bg-slate-900/60 border-t border-slate-800 flex items-center justify-end gap-3">
          <button
            onClick={() => onRespond(approval.id, false)}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-slate-800/90 hover:bg-slate-800 text-slate-300 hover:text-white border border-slate-700 transition-all font-mono text-xs cursor-pointer"
          >
            <XCircle className="w-4 h-4 text-slate-400" />
            <span>Abort (Esc)</span>
          </button>

          <button
            onClick={() => onRespond(approval.id, true)}
            className="flex items-center gap-2 px-5 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-emerald-600 hover:from-amber-400 hover:to-emerald-500 text-slate-950 font-bold font-mono text-xs shadow-lg shadow-amber-500/20 transition-all cursor-pointer"
          >
            <CheckCircle2 className="w-4 h-4 text-slate-950" />
            <span>Authorize (Enter)</span>
          </button>
        </div>
      </div>
    </div>
  );
}
