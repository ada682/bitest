"use client";
import { useState } from "react";
import { StatusDot } from "./Badges";
import PinModal from "./PinModal";

interface HeaderProps {
  status:          string;
  currentSymbol?:  string | null;
  scanned?:        number;
  total?:          number;
  onStart:         () => void;
  onStop:          () => void;
  onReset:         () => void;
  running:         boolean;
  onMenuToggle:    () => void;
}

export default function Header({
  status, currentSymbol, scanned, total,
  onStart, onStop, onReset,
  running,
  onMenuToggle,
}: HeaderProps) {
  const [showPinModal, setShowPinModal] = useState<"start" | "stop" | "reset" | null>(null);

  const handlePinSuccess = () => {
    if (showPinModal === "start") onStart();
    if (showPinModal === "stop")  onStop();
    if (showPinModal === "reset") onReset();
  };

  return (
    <>
      <header className="h-14 border-b border-border bg-surface/80 backdrop-blur flex items-center px-3 sm:px-6 gap-2 sm:gap-4 sticky top-0 z-10">
        {/* Hamburger — mobile only */}
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 rounded-lg text-muted hover:text-text hover:bg-white/5 transition-colors"
          aria-label="Open menu"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <StatusDot status={status} />

        {running && currentSymbol && (
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted font-mono">
            <span className="text-subtle">Scanning</span>
            <span className="text-text font-medium">{currentSymbol}</span>
            {total ? (
              <span className="text-muted/60">{scanned}/{total}</span>
            ) : null}
          </div>
        )}

        <div className="flex-1" />

        {/* Controls */}
        <div className="flex items-center gap-1.5 sm:gap-2">
          <button
            onClick={() => setShowPinModal("reset")}
            className="px-2.5 sm:px-3 py-1.5 text-xs font-medium text-warning border border-warning/30 hover:bg-warning/10 rounded-lg transition-colors"
          >
            <span className="hidden xs:inline">Reset</span>
            <svg className="xs:hidden w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
          </button>

          {running ? (
            <button
              onClick={() => setShowPinModal("stop")}
              className="px-2.5 sm:px-3 py-1.5 text-xs font-medium text-danger border border-danger/30 hover:bg-danger/10 rounded-lg transition-colors"
            >
              Stop
            </button>
          ) : (
            <button
              onClick={() => setShowPinModal("start")}
              className="px-2.5 sm:px-3 py-1.5 text-xs font-medium text-bg bg-accent hover:bg-accent/90 rounded-lg transition-colors font-semibold"
            >
              Start
            </button>
          )}
        </div>
      </header>

      <PinModal
        isOpen={showPinModal !== null}
        onClose={() => setShowPinModal(null)}
        onSuccess={handlePinSuccess}
        action={showPinModal || "start"}
      />
    </>
  );
}
