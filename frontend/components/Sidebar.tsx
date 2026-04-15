"use client";
import clsx from "clsx";

type View = "dashboard" | "history";

interface SidebarProps {
  active:   View;
  onChange: (v: View) => void;
}

const nav: { id: View; label: string; icon: string }[] = [
  { id: "dashboard", label: "Dashboard",       icon: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" },
  { id: "history",   label: "Signal History",  icon: "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" },
];

export default function Sidebar({ active, onChange }: SidebarProps) {
  return (
    <aside className="fixed top-0 left-0 h-full w-56 bg-surface border-r border-border flex flex-col z-20">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-lg bg-accent/20 border border-accent/30 flex items-center justify-center">
            <svg className="w-4 h-4 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8}
                d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
            </svg>
          </div>
          <span className="text-sm font-semibold text-text tracking-tight">CryptoSignals</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-4 px-3 flex flex-col gap-0.5">
        {nav.map(({ id, label, icon }) => (
          <button
            key={id}
            onClick={() => onChange(id)}
            className={clsx(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 text-left",
              active === id
                ? "bg-accent/10 text-accent border border-accent/20"
                : "text-subtle hover:bg-white/5 hover:text-text",
            )}
          >
            <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d={icon} />
            </svg>
            {label}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-5 py-4 border-t border-border">
        <p className="text-[10px] text-muted font-mono">MEXC Futures</p>
        <p className="text-[10px] text-muted/60 mt-0.5">AI Signal Scanner</p>
      </div>
    </aside>
  );
}
