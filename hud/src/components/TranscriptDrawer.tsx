import { useState, useRef, useEffect } from "react";
import type { KeyboardEvent } from "react";
import { MessageSquare, ChevronUp, ChevronDown, Volume2, Send, Zap, Sparkles } from "lucide-react";
import type { AlfredStatus } from "../types";

interface TranscriptDrawerProps {
  transcript: string;
  status: AlfredStatus;
  onSendTextPrompt?: (text: string) => void;
  onPulseRms?: (intensity?: number) => void;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export function TranscriptDrawer({
  transcript,
  status,
  onSendTextPrompt,
  onPulseRms,
  onMouseEnter,
  onMouseLeave,
}: TranscriptDrawerProps) {
  const [isOpen, setIsOpen] = useState(true);
  const [inputText, setInputText] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  const handleSend = () => {
    if (!inputText.trim() || !onSendTextPrompt) return;
    onSendTextPrompt(inputText);
    setInputText("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="w-full max-w-3xl mx-auto rounded-2xl bg-slate-950/85 backdrop-blur-xl border border-cyan-500/30 shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden transition-all duration-300"
    >
      {/* Header Bar */}
      <div
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2.5 flex items-center justify-between cursor-pointer select-none bg-slate-900/60 hover:bg-slate-900/90 border-b border-cyan-500/20 text-xs transition-colors"
      >
        <div className="flex items-center gap-2">
          <MessageSquare className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-mono text-cyan-200 tracking-wider font-semibold text-[11px]">
            EXECUTIVE DIALOGUE & TRANSCRIPTION
          </span>
          {status === "speaking" && (
            <span className="flex items-center gap-1 text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
              <Volume2 className="w-3 h-3 animate-pulse" />
              VOCALIZING
            </span>
          )}
        </div>
        <div className="text-slate-400 hover:text-cyan-300">
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </div>
      </div>

      {/* Collapsible Content */}
      {isOpen && (
        <div className="flex flex-col">
          {/* Transcript Scroll Area */}
          <div
            ref={scrollRef}
            className="p-4 max-h-40 overflow-y-auto scrollbar-thin scrollbar-thumb-cyan-500/20 scrollbar-track-transparent font-mono text-xs leading-relaxed text-slate-200"
          >
            {transcript ? (
              <div className="space-y-2">
                <div className="flex items-start gap-2">
                  <span className="text-cyan-400 select-none font-bold">›</span>
                  <p className="whitespace-pre-wrap selection:bg-cyan-500/30 selection:text-white">
                    {transcript}
                  </p>
                </div>
              </div>
            ) : (
              <div className="text-slate-500 italic flex items-center gap-2">
                <span className="text-slate-600">›</span>
                <span>Awaiting vocal directive, Sir...</span>
              </div>
            )}
          </div>

          {/* Quick-Test Simulation & Text Prompt Toolbar */}
          <div className="px-4 py-2.5 bg-slate-900/70 border-t border-cyan-500/20 flex flex-col gap-2">
            {/* Simulation Action Chips */}
            <div className="flex items-center gap-1.5 flex-wrap text-[10px] font-mono">
              <span className="text-slate-400 flex items-center gap-1 mr-1">
                <Sparkles className="w-3 h-3 text-cyan-400" />
                Quick Test:
              </span>

              {onPulseRms && (
                <button
                  type="button"
                  onClick={() => onPulseRms(0.85)}
                  className="flex items-center gap-1 px-2 py-1 rounded bg-slate-800 hover:bg-cyan-950/60 text-cyan-300 border border-cyan-500/30 transition-colors cursor-pointer"
                  title="Simulate microphone audio spike to test 60 FPS Gyroscope Orb"
                >
                  <Zap className="w-3 h-3 text-amber-400" />
                  <span>Pulse RMS (0.85)</span>
                </button>
              )}

              {onSendTextPrompt && (
                <>
                  <button
                    type="button"
                    onClick={() => onSendTextPrompt("Status report, Alfred.")}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer"
                  >
                    "Status report"
                  </button>
                  <button
                    type="button"
                    onClick={() => onSendTextPrompt("Inspect active screen.")}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer"
                  >
                    "Inspect screen"
                  </button>
                  <button
                    type="button"
                    onClick={() => onSendTextPrompt("Check system diagnostics.")}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer"
                  >
                    "Diagnostics"
                  </button>
                </>
              )}
            </div>

            {/* Manual Text Prompt Input */}
            {onSendTextPrompt && (
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={inputText}
                    onChange={(e) => setInputText(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder="Send executive directive or prompt to Gemini Live session..."
                    className="w-full bg-slate-950/80 border border-cyan-500/30 rounded-xl px-3 py-1.5 font-mono text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!inputText.trim()}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-slate-950 font-bold font-mono text-xs transition-all cursor-pointer shadow-md shadow-cyan-500/20"
                >
                  <Send className="w-3.5 h-3.5 text-slate-950" />
                  <span>Send</span>
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
