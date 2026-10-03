import { cn } from "@/lib/utils";
import { Lock, CheckCircle2, KeyRound, AlertTriangle, FileCheck2 } from "lucide-react";

const MAP = {
  locked: { label: "Locked", dot: "bg-rose-500", cls: "bg-rose-500/15 text-rose-300 border-rose-500/30", Icon: Lock },
  matched: { label: "Matched", dot: "bg-indigo-400 pulse-dot", cls: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30", Icon: KeyRound },
  unlocked: { label: "Unlocked", dot: "bg-emerald-500", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30", Icon: CheckCircle2 },
  ready: { label: "No Password", dot: "bg-slate-400", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30", Icon: FileCheck2 },
  error: { label: "Error", dot: "bg-rose-600", cls: "bg-rose-600/20 text-rose-200 border-rose-600/40", Icon: AlertTriangle },
};

export const StatusBadge = ({ status, testid }) => {
  const s = MAP[status] || MAP.ready;
  const Icon = s.Icon;
  return (
    <span
      data-testid={testid}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold font-mono-c",
        s.cls,
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
      <Icon className="h-3 w-3" />
      {s.label}
    </span>
  );
};
