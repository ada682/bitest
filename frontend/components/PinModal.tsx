"use client";
import { useState, useEffect } from "react";
import clsx from "clsx";
import { verifyPin } from "@/lib/api";

interface PinModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  action: "start" | "stop" | "reset";
}

export default function PinModal({ isOpen, onClose, onSuccess, action }: PinModalProps) {
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [shake, setShake] = useState(false);

  // Reset state when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setPin("");
      setError("");
      setLoading(false);
      setShake(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (pin.length === 0) {
      setError("PIN required");
      triggerShake();
      return;
    }

    setLoading(true);
    setError("");

    try {
      const isValid = await verifyPin(pin);
      if (isValid) {
        onSuccess();
        onClose();
      } else {
        setError("Invalid PIN");
        triggerShake();
      }
    } catch {
      setError("Verification failed");
      triggerShake();
    } finally {
      setLoading(false);
    }
  };

  const triggerShake = () => {
    setShake(true);
    setTimeout(() => setShake(false), 500);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  };

  // Action-specific colors and text
  const actionConfig = {
    start: {
      title: "Start Bot",
      description: "Enter PIN to start scanning",
      buttonText: "Confirm Start",
      iconPath: "M5 13l4 4L19 7",
      iconColor: "text-accent",
      buttonColor: "bg-accent hover:bg-accent/90",
    },
    stop: {
      title: "Stop Bot",
      description: "Enter PIN to stop the bot",
      buttonText: "Confirm Stop",
      iconPath: "M6 18L18 6M6 6l12 12",
      iconColor: "text-danger",
      buttonColor: "bg-danger hover:bg-danger/90",
    },
    reset: {
      title: "Reset Stats",
      description: "Enter PIN to reset all statistics",
      buttonText: "Confirm Reset",
      iconPath: "M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15",
      iconColor: "text-warning",
      buttonColor: "bg-warning hover:bg-warning/90 text-bg",
    },
  };

  const config = actionConfig[action];

  if (!isOpen) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 transition-all duration-300"
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-full max-w-sm"
        onKeyDown={handleKeyDown}
      >
        <div
          className={clsx(
            "bg-card border border-border rounded-2xl shadow-2xl overflow-hidden transition-all duration-300",
            shake && "animate-shake"
          )}
        >
          {/* Header */}
          <div className="px-6 py-4 border-b border-border bg-surface/50">
            <div className="flex items-center gap-3">
              <div className={clsx(
                "w-8 h-8 rounded-full border flex items-center justify-center",
                action === "start" && "bg-accent/10 border-accent/20",
                action === "stop" && "bg-danger/10 border-danger/20",
                action === "reset" && "bg-warning/10 border-warning/20",
              )}>
                <svg className={clsx("w-4 h-4", config.iconColor)} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d={config.iconPath} />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-semibold text-text">{config.title}</h3>
                <p className="text-[10px] text-muted mt-0.5">{config.description}</p>
              </div>
            </div>
          </div>

          {/* Body */}
          <form onSubmit={handleSubmit} className="p-6">
            <div className="mb-6">
              <label className="block text-[10px] font-mono uppercase tracking-wider text-muted mb-2">
                Security PIN
              </label>
              <input
                type="password"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={6}
                value={pin}
                onChange={(e) => {
                  setPin(e.target.value.replace(/[^0-9]/g, ""));
                  setError("");
                }}
                className={clsx(
                  "w-full bg-bg border rounded-xl px-4 py-3 text-text font-mono text-center text-lg tracking-wider",
                  "focus:outline-none focus:border-accent/50 transition-all duration-200",
                  error ? "border-danger/50 focus:border-danger" : "border-border focus:border-accent/50"
                )}
                placeholder="••••••"
                autoFocus
              />
              {error && (
                <p className="text-[10px] text-danger mt-2 flex items-center gap-1">
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                      d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {error}
                </p>
              )}
            </div>

            {/* Buttons */}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2.5 rounded-xl text-xs font-medium text-muted hover:text-text hover:bg-white/5 transition-all duration-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={loading}
                className={clsx(
                  "flex-1 px-4 py-2.5 rounded-xl text-xs font-semibold transition-all duration-200",
                  config.buttonColor,
                  loading && "opacity-70 cursor-not-allowed"
                )}
              >
                {loading ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Verifying...
                  </span>
                ) : (
                  config.buttonText
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}
