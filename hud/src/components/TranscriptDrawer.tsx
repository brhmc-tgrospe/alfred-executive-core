import { useState, useRef, useEffect } from "react";
import { MessageSquare, ChevronUp, ChevronDown, Volume2 } from "lucide-react";
import type { AlfredStatus } from "../types";

interface TranscriptDrawerProps {
  transcript: string;
  status: AlfredStatus;
  onMouseEnter?: () => void;
  onMouseLeave?: () => void;
}

export function TranscriptDrawer({
  transcript,
  status,
  onMouseEnter,
  onMouseLeave,
}: TranscriptDrawerProps) {
  const [isOpen, setIsOpen] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

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
        <div
          ref={scrollRef}
          className="p-4 max-h-48 overflow-y-auto scrollbar-thin scrollbar-thumb-cyan-500/20 scrollbar-track-transparent font-mono text-xs leading-relaxed text-slate-200"
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
      )}
    </div>
  );
}
