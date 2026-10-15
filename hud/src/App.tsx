import { useState, useCallback, useEffect } from "react";
import { useAlfredWs } from "./hooks/useAlfredWs";
import { AudioOrb } from "./components/AudioOrb";
import { TelemetryBar } from "./components/TelemetryBar";
import { TranscriptDrawer } from "./components/TranscriptDrawer";
import { ApprovalModal } from "./components/ApprovalModal";
import { Sliders, Play, Volume2, ShieldAlert } from "lucide-react";
import type { AlfredStatus } from "./types";

export function App() {
  const {
    state,
    connected,
    micActive,
    toggleMic,
    sendApproval,
    sendInspectScreen,
    sendTextPrompt,
    pulseRms,
    simulateApproval: sendSimulateApproval,
    injectMockState,
  } = useAlfredWs();

  const getElectronBridge = () => {
    if (typeof window !== "undefined") {
      return window.alfredElectron || window.electronAPI;
    }
    return undefined;
  };

  // Show simulation controls when running in web browser without Electron
  const isElectron = typeof window !== "undefined" && Boolean(getElectronBridge());
  const [showSimControls, setShowSimControls] = useState<boolean>(!isElectron);
  const [clickThroughLocked, setClickThroughLocked] = useState<boolean>(false);

  // Toggle-to-Talk via Electron IPC or browser Ctrl+Space
  useEffect(() => {
    const electron = getElectronBridge();
    if (electron?.onPttTriggered) {
      const unsubscribe = electron.onPttTriggered(() => {
        toggleMic();
      });
      return unsubscribe;
    }

    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.ctrlKey && e.code === "Space") {
        e.preventDefault();
        toggleMic();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggleMic]);

  // Mouse event IPC forwarder for Electron transparent overlay
  const handlePanelMouseEnter = useCallback(() => {
    const electron = getElectronBridge();
    if (electron) {
      electron.setIgnoreMouseEvents(false);
    }
  }, []);

  const handlePanelMouseLeave = useCallback(() => {
    if (clickThroughLocked) return;
    const electron = getElectronBridge();
    if (electron) {
      electron.setIgnoreMouseEvents(true, { forward: true });
    }
  }, [clickThroughLocked]);

  const toggleClickThrough = useCallback(() => {
    setClickThroughLocked((prev) => {
      const next = !prev;
      const electron = getElectronBridge();
      if (electron) {
        if (next) {
          electron.setIgnoreMouseEvents(false);
        } else {
          electron.setIgnoreMouseEvents(true, { forward: true });
        }
      }
      return next;
    });
  }, []);

  // Simulation helpers for verification
  const simulateState = (status: AlfredStatus, rms: number, transcript: string) => {
    injectMockState({
      status,
      rms_volume: rms,
      transcript,
      active_tool: status === "thinking" ? "inspect_active_screen" : null,
      pending_approval: null,
    });
  };

  const handleSimulateApproval = () => {
    if (connected) {
      sendSimulateApproval();
    } else {
      injectMockState({
        status: "thinking",
        rms_volume: 0.1,
        transcript: "I require your executive clearance to terminate anomalous background worker tasks, Sir.",
        active_tool: "execute_terminal_command",
        pending_approval: {
          id: `req-${Math.floor(1000 + Math.random() * 9000)}`,
          action: "execute_terminal_command",
          command: "Stop-Process -Name 'rogue_process' -Force",
          risk_level: "HIGH",
        },
      });
    }
  };

  return (
    <main className="w-screen h-screen relative flex flex-col justify-between p-6 overflow-hidden pointer-events-none select-none bg-transparent">
      {/* 1. Top Telemetry Bar with Toggle-to-Talk & Interactivity Lock */}
      <div className="w-full flex justify-center pointer-events-auto">
        <TelemetryBar
          status={state.status}
          cpu={state.cpu}
          ram={state.ram}
          activeTool={state.active_tool}
          connected={connected}
          micActive={micActive}
          clickThroughLocked={clickThroughLocked}
          onToggleMic={toggleMic}
          onToggleClickThrough={toggleClickThrough}
          onInspectScreen={sendInspectScreen}
          onMouseEnter={handlePanelMouseEnter}
          onMouseLeave={handlePanelMouseLeave}
        />
      </div>

      {/* 2. Center 60 FPS Vanilla Three.js Gyroscope Orb */}
      <div className="flex-1 flex flex-col items-center justify-center relative">
        <div className="pointer-events-auto">
          <AudioOrb
            rmsVolume={state.rms_volume}
            status={state.status}
            size={320}
          />
        </div>

        {/* Ambient HUD Subtitle / Status Display */}
        <div className="mt-3 flex items-center gap-2 pointer-events-none">
          <span className="font-mono text-xs tracking-widest text-cyan-400/80 uppercase">
            A.L.F.R.E.D.
          </span>
          <span className="text-slate-600">|</span>
          <span className="font-mono text-xs tracking-widest text-slate-400 uppercase">
            {state.status === "speaking"
              ? "Synthesizing Vocal Response"
              : state.status === "thinking"
              ? "Executing Cognitive Reasoning"
              : state.status === "listening"
              ? "Acoustic Sensors Active"
              : "Standing By"}
          </span>
        </div>
      </div>

      {/* 3. Bottom Scrolling Transcript Drawer with Simulation Toolbar */}
      <div className="w-full flex justify-center pointer-events-auto">
        <TranscriptDrawer
          transcript={state.transcript}
          status={state.status}
          onSendTextPrompt={sendTextPrompt}
          onPulseRms={pulseRms}
          onMouseEnter={handlePanelMouseEnter}
          onMouseLeave={handlePanelMouseLeave}
        />
      </div>

      {/* 4. High-Priority 30-Second Security Approval Modal */}
      {state.pending_approval && (
        <div className="pointer-events-auto">
          <ApprovalModal
            key={state.pending_approval.id}
            approval={state.pending_approval}
            onRespond={sendApproval}
            onMouseEnter={handlePanelMouseEnter}
            onMouseLeave={handlePanelMouseLeave}
          />
        </div>
      )}

      {/* 5. Browser Simulation Control Strip (for verification in headless/browser preview) */}
      <aside
        onMouseEnter={handlePanelMouseEnter}
        onMouseLeave={handlePanelMouseLeave}
        className="fixed bottom-4 right-4 z-40 pointer-events-auto"
      >
        {showSimControls ? (
          <div className="p-3 rounded-xl bg-slate-950/90 backdrop-blur-xl border border-cyan-500/30 shadow-2xl flex flex-col gap-2 font-mono text-[11px]">
            <div className="flex items-center justify-between gap-4 text-cyan-300 font-bold border-b border-cyan-500/20 pb-1.5">
              <span className="flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5" />
                SIMULATION SUITE
              </span>
              <button
                onClick={() => setShowSimControls(false)}
                className="text-slate-400 hover:text-white px-1"
              >
                ✕
              </button>
            </div>
            <div className="grid grid-cols-2 gap-1.5 pt-1">
              <button
                onClick={() =>
                  simulateState("idle", 0.0, "Core standing by. All systems operating at peak efficiency.")
                }
                className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-cyan-950/60 text-cyan-300 border border-cyan-500/30 text-left transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Play className="w-3 h-3 text-cyan-400" />
                <span>Sim Idle</span>
              </button>
              <button
                onClick={() =>
                  simulateState("speaking", 0.72, "Right away, Sir. Initiating full telemetry diagnostics.")
                }
                className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-emerald-950/60 text-emerald-300 border border-emerald-500/30 text-left transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Volume2 className="w-3 h-3 text-emerald-400" />
                <span>Sim Speak</span>
              </button>
              <button
                onClick={() =>
                  simulateState("thinking", 0.25, "Consulting executive database and inspecting monitor buffer...")
                }
                className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-amber-950/60 text-amber-300 border border-amber-500/30 text-left transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Sliders className="w-3 h-3 text-amber-400" />
                <span>Sim Think</span>
              </button>
              <button
                onClick={handleSimulateApproval}
                className="px-2.5 py-1.5 rounded bg-slate-900 hover:bg-red-950/60 text-rose-300 border border-rose-500/30 text-left transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <ShieldAlert className="w-3 h-3 text-rose-400" />
                <span>Sim Gate</span>
              </button>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setShowSimControls(true)}
            className="p-2 rounded-xl bg-slate-950/80 backdrop-blur-md border border-cyan-500/30 text-cyan-400 hover:text-cyan-200 hover:bg-slate-900 transition-all cursor-pointer shadow-lg"
            title="Open Simulation Controls"
          >
            <Sliders className="w-4 h-4" />
          </button>
        )}
      </aside>
    </main>
  );
}

export default App;
