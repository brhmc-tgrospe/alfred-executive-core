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
      className="hud-interactive w-full max-w-3xl mx-auto rounded-2xl bg-slate-950/85 backdrop-blur-xl border border-cyan-500/30 shadow-[0_8px_32px_rgba(0,0,0,0.6)] overflow-hidden transition-all duration-300"
    >
      {/* Header Bar with Integrated Quick-Test Chips */}
      <div className="px-3 py-1.5 flex items-center justify-between select-none bg-slate-900/70 border-b border-cyan-500/20 text-xs transition-colors gap-2">
        {/* Left: Title & Vocalizing Status */}
        <div
          onClick={() => setIsOpen(!isOpen)}
          className="flex items-center gap-2 cursor-pointer shrink-0"
        >
          <MessageSquare className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-mono text-cyan-200 tracking-wider font-semibold text-[11px] hidden sm:inline">
            EXECUTIVE DIALOGUE
          </span>
          {status === "speaking" && (
            <span className="flex items-center gap-1 text-[9px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded border border-emerald-500/20">
              <Volume2 className="w-3 h-3 animate-pulse" />
              VOCALIZING
            </span>
          )}
        </div>

        {/* Middle: Quick Test Action Chips in Header */}
        <div
          className="flex items-center gap-1 text-[9px] font-mono overflow-x-auto scrollbar-none"
          onClick={(e) => e.stopPropagation()}
        >
          <span className="text-slate-400 flex items-center gap-1 shrink-0 mr-0.5">
            <Sparkles className="w-3 h-3 text-cyan-400" />
            <span className="hidden md:inline">Quick Test:</span>
          </span>

          {onPulseRms && (
            <button
              type="button"
              onClick={() => onPulseRms(0.85)}
              className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-slate-800/90 hover:bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 transition-colors cursor-pointer shrink-0"
              title="Simulate microphone audio spike to test 60 FPS Gyroscope Orb"
            >
              <Zap className="w-2.5 h-2.5 text-amber-400" />
              <span>Pulse RMS</span>
            </button>
          )}

          {onSendTextPrompt && (
            <>
              <button
                type="button"
                onClick={() => onSendTextPrompt("Status report, Alfred.")}
                className="px-1.5 py-0.5 rounded bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer shrink-0"
              >
                "Status report"
              </button>
              <button
                type="button"
                onClick={() => onSendTextPrompt("Inspect active screen.")}
                className="px-1.5 py-0.5 rounded bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer shrink-0"
              >
                "Inspect screen"
              </button>
              <button
                type="button"
                onClick={() => onSendTextPrompt("Check system diagnostics.")}
                className="px-1.5 py-0.5 rounded bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 transition-colors cursor-pointer shrink-0"
              >
                "Diagnostics"
              </button>
            </>
          )}
        </div>

        {/* Right: Accordion Toggle Chevron */}
        <div
          onClick={() => setIsOpen(!isOpen)}
          className="text-slate-400 hover:text-cyan-300 cursor-pointer pl-1 shrink-0"
        >
          {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
        </div>
      </div>

      {/* Sleek Low-Profile Collapsible Content */}
      {isOpen && (
        <div className="flex flex-col">
          {/* Transcript Scroll Area */}
          <div
            ref={scrollRef}
            className="p-3 max-h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-cyan-500/20 scrollbar-track-transparent font-mono text-xs leading-relaxed text-slate-200"
          >
            {transcript ? (
              <div className="space-y-1.5">
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

          {/* Manual Text Prompt Input */}
          {onSendTextPrompt && (
            <div className="px-3 py-1.5 bg-slate-900/80 border-t border-cyan-500/20 flex items-center gap-2">
              <div className="relative flex-1">
                <input
                  type="text"
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Send executive directive or prompt to Gemini Live session..."
                  className="w-full bg-slate-950/80 border border-cyan-500/30 rounded-xl px-3 py-1 font-mono text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400 transition-all"
                />
              </div>
              <button
                type="button"
                onClick={handleSend}
                disabled={!inputText.trim()}
                className="flex items-center gap-1.5 px-3 py-1 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-slate-950 font-bold font-mono text-xs transition-all cursor-pointer shadow-md shadow-cyan-500/20"
              >
                <Send className="w-3.5 h-3.5 text-slate-950" />
                <span>Send</span>
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
