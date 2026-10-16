import { useState, useCallback, useEffect, useRef } from "react";
import { useAlfredWs } from "./hooks/useAlfredWs";
import { useFps } from "./hooks/useFps";
import { AudioOrb } from "./components/AudioOrb";
import { TelemetryBar } from "./components/TelemetryBar";
import { TranscriptDrawer } from "./components/TranscriptDrawer";
import { ApprovalModal } from "./components/ApprovalModal";
import { Sliders, Play, Volume2, ShieldAlert } from "lucide-react";
import type { AlfredStatus, LayoutMode } from "./types";

interface OrbPosition {
  x: number;
  y: number;
}

export function App() {
  const {
    state,
    connected,
    micActive,
    toggleMic,
    switchInputDevice,
    sendApproval,
    sendInspectScreen,
    sendTextPrompt,
    pulseRms,
    simulateApproval: sendSimulateApproval,
    injectMockState,
  } = useAlfredWs();

  const fps = useFps();

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
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("cinema");
  const [stealthEnabled, setStealthEnabled] = useState<boolean>(true);

  // Persistent & Resizable Orb Size (100px - 500px, default 280px)
  const [orbSize, setOrbSize] = useState<number>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("alfred_orb_size");
      if (saved) {
        const parsed = Number(saved);
        if (!isNaN(parsed) && parsed >= 100 && parsed <= 500) {
          return parsed;
        }
      }
    }
    return 280;
  });

  // Persistent Draggable Orb Position
  const [orbPos, setOrbPos] = useState<OrbPosition | null>(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("alfred_orb_pos");
      if (saved) {
        try {
          const parsed = JSON.parse(saved);
          if (typeof parsed?.x === "number" && typeof parsed?.y === "number") {
            return parsed;
          }
        } catch {}
      }
    }
    return null;
  });

  const updateOrbPos = useCallback((newPos: OrbPosition | null) => {
    setOrbPos(newPos);
    if (typeof window !== "undefined") {
      if (newPos) {
        localStorage.setItem("alfred_orb_pos", JSON.stringify(newPos));
      } else {
        localStorage.removeItem("alfred_orb_pos");
      }
    }
  }, []);

  const updateOrbSize = useCallback((updater: number | ((prev: number) => number)) => {
    setOrbSize((prev) => {
      const nextVal = typeof updater === "function" ? updater(prev) : updater;
      const clamped = Math.max(100, Math.min(500, Math.round(nextVal)));
      if (typeof window !== "undefined") {
        localStorage.setItem("alfred_orb_size", clamped.toString());
      }
      return clamped;
    });
  }, []);

  // Compute actual coordinates with fallback defaults
  const actualX =
    orbPos !== null
      ? orbPos.x
      : layoutMode === "docked"
      ? typeof window !== "undefined"
        ? Math.max(10, window.innerWidth - orbSize - 40)
        : 800
      : typeof window !== "undefined"
      ? Math.max(0, Math.round((window.innerWidth - orbSize) / 2))
      : 500;

  const actualY =
    orbPos !== null
      ? orbPos.y
      : layoutMode === "docked"
      ? typeof window !== "undefined"
        ? Math.max(10, window.innerHeight - orbSize - 140)
        : 500
      : typeof window !== "undefined"
      ? Math.max(0, Math.round((window.innerHeight - orbSize) / 2 - 20))
      : 300;

  // Window resize bounds clamping
  useEffect(() => {
    const handleWindowResize = () => {
      setOrbPos((prev) => {
        if (!prev) return prev;
        const clampedX = Math.max(10, Math.min(window.innerWidth - orbSize - 10, prev.x));
        const clampedY = Math.max(10, Math.min(window.innerHeight - orbSize - 10, prev.y));
        if (clampedX !== prev.x || clampedY !== prev.y) {
          const next = { x: clampedX, y: clampedY };
          localStorage.setItem("alfred_orb_pos", JSON.stringify(next));
          return next;
        }
        return prev;
      });
    };
    window.addEventListener("resize", handleWindowResize);
    return () => window.removeEventListener("resize", handleWindowResize);
  }, [orbSize]);

  // Center reset helper
  const handleResetCenter = useCallback(() => {
    if (typeof window === "undefined") return;
    const centerX = Math.max(0, Math.round((window.innerWidth - orbSize) / 2));
    const centerY = Math.max(0, Math.round((window.innerHeight - orbSize) / 2 - 20));
    updateOrbPos({ x: centerX, y: centerY });
  }, [orbSize, updateOrbPos]);

  // Snap to Docked helper
  const handleSnapDocked = useCallback(() => {
    if (typeof window === "undefined") return;
    const dockedX = Math.max(10, window.innerWidth - orbSize - 40);
    const dockedY = Math.max(10, window.innerHeight - orbSize - 140);
    updateOrbPos({ x: dockedX, y: dockedY });
    setLayoutMode("docked");
  }, [orbSize, updateOrbPos]);

  // Snap to Cinema helper
  const handleSnapCinema = useCallback(() => {
    handleResetCenter();
    setLayoutMode("cinema");
  }, [handleResetCenter]);

  // 3-state layout cycle: cinema -> docked -> orb_only -> cinema
  const toggleLayoutMode = useCallback(() => {
    setLayoutMode((prev) => {
      const next = prev === "cinema" ? "docked" : prev === "docked" ? "orb_only" : "cinema";
      if (next === "docked") {
        const dockedX = Math.max(10, window.innerWidth - orbSize - 40);
        const dockedY = Math.max(10, window.innerHeight - orbSize - 140);
        updateOrbPos({ x: dockedX, y: dockedY });
      } else if (next === "cinema") {
        const centerX = Math.max(0, Math.round((window.innerWidth - orbSize) / 2));
        const centerY = Math.max(0, Math.round((window.innerHeight - orbSize) / 2 - 20));
        updateOrbPos({ x: centerX, y: centerY });
      }
      return next;
    });
  }, [orbSize, updateOrbPos]);

  const toggleStealth = useCallback(() => {
    setStealthEnabled((prev) => {
      const next = !prev;
      const electron = getElectronBridge();
      if (electron?.setContentProtection) {
        electron.setContentProtection(next);
      }
      return next;
    });
  }, []);

  // Global hotkeys (Ctrl+Space for Mic, Ctrl+Shift+A for Layout Mode) and IPC listeners
  useEffect(() => {
    const electron = getElectronBridge();
    const unsubPtt = electron?.onPttTriggered?.(() => {
      toggleMic();
    });
    const unsubLayout = electron?.onToggleLayoutMode?.(() => {
      toggleLayoutMode();
    });
    const unsubSetLayout = electron?.onSetLayoutMode?.((mode: LayoutMode) => {
      setLayoutMode(mode);
    });

    const handleKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.ctrlKey && e.code === "Space") {
        e.preventDefault();
        toggleMic();
      } else if (e.ctrlKey && e.shiftKey && (e.code === "KeyA" || e.key === "A" || e.key === "a")) {
        e.preventDefault();
        toggleLayoutMode();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      unsubPtt?.();
      unsubLayout?.();
      unsubSetLayout?.();
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [toggleMic, toggleLayoutMode]);

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

  // Pointer Dragging for AudioOrb
  const isDraggingRef = useRef(false);
  const dragStartRef = useRef<{ startX: number; startY: number; orbX: number; orbY: number }>({
    startX: 0,
    startY: 0,
    orbX: 0,
    orbY: 0,
  });

  const handleOrbPointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.button !== 0) return;
      if ((e.target as HTMLElement).closest("button, input, select, a")) return;

      isDraggingRef.current = true;
      dragStartRef.current = {
        startX: e.clientX,
        startY: e.clientY,
        orbX: actualX,
        orbY: actualY,
      };

      const electron = getElectronBridge();
      if (electron) {
        electron.setIgnoreMouseEvents(false);
      }

      const onPointerMove = (moveEvent: PointerEvent) => {
        if (!isDraggingRef.current) return;
        const dx = moveEvent.clientX - dragStartRef.current.startX;
        const dy = moveEvent.clientY - dragStartRef.current.startY;
        const newX = Math.round(dragStartRef.current.orbX + dx);
        const newY = Math.round(dragStartRef.current.orbY + dy);
        const clampedX = Math.max(
          -Math.round(orbSize / 2),
          Math.min(window.innerWidth - Math.round(orbSize / 2), newX)
        );
        const clampedY = Math.max(
          -Math.round(orbSize / 2),
          Math.min(window.innerHeight - Math.round(orbSize / 2), newY)
        );
        updateOrbPos({ x: clampedX, y: clampedY });
      };

      const onPointerUp = () => {
        isDraggingRef.current = false;
        window.removeEventListener("pointermove", onPointerMove);
        window.removeEventListener("pointerup", onPointerUp);
      };

      window.addEventListener("pointermove", onPointerMove);
      window.addEventListener("pointerup", onPointerUp);
    },
    [actualX, actualY, orbSize, updateOrbPos]
  );

  // Mouse wheel resize (±16px per notch)
  const handleOrbWheel = useCallback(
    (e: React.WheelEvent<HTMLDivElement>) => {
      e.preventDefault();
      e.stopPropagation();
      const step = e.deltaY < 0 ? 16 : -16;
      updateOrbSize((prev) => prev + step);
    },
    [updateOrbSize]
  );

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
      {/* 1. Top Telemetry Bar with Toggle-to-Talk & Interactivity Lock (Hidden in Orb-Only mode) */}
      {layoutMode !== "orb_only" && (
        <div className="w-full flex justify-center pointer-events-auto">
          <TelemetryBar
            status={state.status}
            cpu={state.cpu}
            ram={state.ram}
            pingMs={state.ping_ms}
            fps={fps}
            rmsVolume={state.rms_volume}
            inputDevices={state.input_devices}
            currentDeviceId={state.current_device_id}
            onSwitchInputDevice={switchInputDevice}
            activeTool={state.active_tool}
            connected={connected}
            micActive={micActive}
            clickThroughLocked={clickThroughLocked}
            layoutMode={layoutMode}
            stealthEnabled={stealthEnabled}
            onToggleMic={toggleMic}
            onToggleClickThrough={toggleClickThrough}
            onToggleLayout={toggleLayoutMode}
            onToggleStealth={toggleStealth}
            onInspectScreen={sendInspectScreen}
            onMouseEnter={handlePanelMouseEnter}
            onMouseLeave={handlePanelMouseLeave}
          />
        </div>
      )}

      {/* Spacer to preserve flex structure between top bar and bottom drawer */}
      <div className="flex-1 pointer-events-none" />

      {/* 2. Freely Draggable & Resizable 3D AudioOrb (Position: Fixed across all modes) */}
      <div
        style={{
          position: "fixed",
          left: `${actualX}px`,
          top: `${actualY}px`,
          width: `${orbSize}px`,
          height: `${orbSize}px`,
          touchAction: "none",
        }}
        onPointerDown={handleOrbPointerDown}
        onWheel={handleOrbWheel}
        onMouseEnter={handlePanelMouseEnter}
        onMouseLeave={handlePanelMouseLeave}
        className="group z-30 pointer-events-auto flex items-center justify-center cursor-grab active:cursor-grabbing select-none"
        title="Click & Drag to move anywhere on desktop. Scroll wheel or use hover pill to resize."
      >
        <AudioOrb rmsVolume={state.rms_volume} status={state.status} size={orbSize} />

        {/* Ambient Mode Subtitle / Status Display */}
        {layoutMode === "cinema" ? (
          <div className="absolute -top-6 left-1/2 -translate-x-1/2 flex items-center gap-1.5 pointer-events-none whitespace-nowrap opacity-80 font-mono text-[10px] tracking-widest uppercase">
            <span className="text-cyan-400 font-semibold">A.L.F.R.E.D.</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">
              {state.status === "speaking"
                ? "Synthesizing Vocal Response"
                : state.status === "thinking"
                ? "Executing Cognitive Reasoning"
                : state.status === "listening"
                ? "Acoustic Sensors Active"
                : "Standing By"}
            </span>
          </div>
        ) : layoutMode === "docked" ? (
          <div className="absolute -top-5 left-1/2 -translate-x-1/2 flex items-center gap-1.5 pointer-events-none font-mono text-[9px] tracking-widest text-cyan-400/90 uppercase whitespace-nowrap">
            <span>DOCKED</span>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400 capitalize">{state.status}</span>
          </div>
        ) : null}

        {/* Hover Mini-Pill: [-], [+], Size readout, [Center], and Mode Switchers */}
        <div
          onPointerDown={(e) => e.stopPropagation()}
          className="absolute -bottom-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-slate-950/90 backdrop-blur-xl border border-cyan-500/40 shadow-[0_4px_24px_rgba(0,0,0,0.85)] text-[10px] font-mono select-none pointer-events-auto z-50 whitespace-nowrap"
        >
          {/* Drag Grip Indicator */}
          <span className="text-slate-500 cursor-grab text-[9px] mr-0.5" title="Drag Orb">
            ⋮⋮
          </span>

          {/* Size Reduction */}
          <button
            type="button"
            onClick={() => updateOrbSize((s) => s - 16)}
            className="w-5 h-5 flex items-center justify-center rounded bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-cyan-300 border border-slate-700/80 cursor-pointer font-bold"
            title="Decrease Orb Size (-16px)"
          >
            -
          </button>

          {/* Size Readout */}
          <span
            className="text-cyan-300 font-bold min-w-[38px] text-center"
            title="Orb Diameter (Scroll mouse wheel to resize)"
          >
            {orbSize}px
          </span>

          {/* Size Increase */}
          <button
            type="button"
            onClick={() => updateOrbSize((s) => s + 16)}
            className="w-5 h-5 flex items-center justify-center rounded bg-slate-900 hover:bg-slate-800 text-slate-300 hover:text-cyan-300 border border-slate-700/80 cursor-pointer font-bold"
            title="Increase Orb Size (+16px)"
          >
            +
          </button>

          <span className="text-slate-600">|</span>

          {/* Center Reset */}
          <button
            type="button"
            onClick={handleResetCenter}
            className="px-1.5 py-0.5 rounded bg-slate-900 hover:bg-cyan-950/60 text-slate-300 hover:text-cyan-300 border border-slate-700/80 cursor-pointer transition-colors"
            title="Reset Orb to Center of Screen"
          >
            Center
          </button>

          <span className="text-slate-600">|</span>

          {/* Mode Switchers */}
          <button
            type="button"
            onClick={handleSnapCinema}
            className={`px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
              layoutMode === "cinema"
                ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
            title="Cinema Mode (Centered Orb + Telemetry + Transcripts)"
          >
            Cinema
          </button>
          <button
            type="button"
            onClick={handleSnapDocked}
            className={`px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
              layoutMode === "docked"
                ? "bg-cyan-500/20 text-cyan-300 font-bold border border-cyan-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
            title="Docked Mode (Bottom-Right Floating Dock)"
          >
            Docked
          </button>
          <button
            type="button"
            onClick={() => setLayoutMode("orb_only")}
            className={`px-1.5 py-0.5 rounded cursor-pointer transition-colors ${
              layoutMode === "orb_only"
                ? "bg-amber-500/20 text-amber-300 font-bold border border-amber-500/40"
                : "text-slate-400 hover:text-slate-200"
            }`}
            title="Orb-Only Mode (Minimalist Floating Orb Only)"
          >
            Orb-Only
          </button>
        </div>
      </div>

      {/* 3. Bottom Scrolling Transcript Drawer with Simulation Toolbar (Hidden in Orb-Only mode) */}
      {layoutMode !== "orb_only" && (
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
      )}

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
