import clsx from "clsx";

type Decision = "LONG" | "SHORT" | "NO TRADE";
type Result   = "TP" | "SL" | null | undefined;

export function DecisionBadge({ decision }: { decision: Decision }) {
  return (
    <span className={clsx(
      "inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold font-mono tracking-wide uppercase",
      decision === "LONG"     && "bg-success/10 text-success border border-success/20",
      decision === "SHORT"    && "bg-danger/10 text-danger border border-danger/20",
      decision === "NO TRADE" && "bg-muted/10 text-muted border border-muted/20",
    )}>
      {decision}
    </span>
  );
}

export function ResultBadge({ result }: { result: Result }) {
  if (!result) return null;
  return (
    <span className={clsx(
      "inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold font-mono tracking-wide uppercase",
      result === "TP" && "bg-success/10 text-success border border-success/20",
      result === "SL" && "bg-danger/10 text-danger border border-danger/20",
    )}>
      {result}
    </span>
  );
}

export function StatusDot({ status }: { status: string }) {
  const online = status === "RUNNING";
  return (
    <span className="relative inline-flex items-center gap-2">
      <span className="relative flex h-2 w-2">
        {online && (
          <span className="pulse-ring absolute inline-flex h-full w-full rounded-full bg-success opacity-75" />
        )}
        <span className={clsx(
          "relative inline-flex rounded-full h-2 w-2",
          online ? "bg-success" : "bg-muted",
        )} />
      </span>
      <span className={clsx(
        "text-xs font-medium",
        online ? "text-success" : "text-muted",
      )}>
        {online ? "Online" : "Offline"}
      </span>
    </span>
  );
}
