"use client";
import { StatusDot } from "./Badges";

interface HeaderProps {
  status:          string;
  currentSymbol?:  string | null;
  scanned?:        number;
  total?:          number;
  onStart:         () => void;
  onStop:          () => void;
  running:         boolean;
}

export default function Header({
  status, currentSymbol, scanned, total,
  onStart, onStop, running,
}: HeaderProps) {
  return (
    <header className="h-14 border-b border-border bg-surface/80 backdrop-blur flex items-center px-6 gap-4 sticky top-0 z-10">
      <StatusDot status={status} />

      {running && currentSymbol && (
        <div className="flex items-center gap-2 text-xs text-muted font-mono">
          <span className="text-subtle">Scanning</span>
          <span className="text-text font-medium">{currentSymbol}</span>
          {total ? (
            <span className="text-muted/60">
              {scanned}/{total}
            </span>
          ) : null}
        </div>
      )}

      <div className="flex-1" />

      {/* Controls */}
      <div className="flex items-center gap-2">
        {running ? (
          <button
            onClick={onStop}
            className="px-3 py-1.5 text-xs font-medium text-danger border border-danger/30 hover:bg-danger/10 rounded-lg transition-colors"
          >
            Stop Bot
          </button>
        ) : (
          <button
            onClick={onStart}
            className="px-3 py-1.5 text-xs font-medium text-bg bg-accent hover:bg-accent/90 rounded-lg transition-colors font-semibold"
          >
            Start Bot
          </button>
        )}
      </div>
    </header>
  );
}
