import { useRef } from "react";
import { StatusBadge } from "./StatusBadge";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";
import { FileText, Sheet, Download, Replace, Trash2, GitMerge } from "lucide-react";
import { cn } from "@/lib/utils";

function fmtSize(b) {
  if (!b) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  let n = b;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${u[i]}`;
}

const ReplaceButton = ({ file, onReplace }) => {
  const ref = useRef(null);
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept=".pdf,.xlsx,.xls,.xlsm,.xlsb"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onReplace(file, f);
          e.target.value = "";
        }}
      />
      <Button
        data-testid={`replace-file-btn-${file.id}`}
        variant="ghost"
        size="icon"
        className="h-8 w-8 text-muted-foreground hover:text-amber-400"
        title="Replace file"
        onClick={() => ref.current?.click()}
      >
        <Replace className="h-4 w-4" />
      </Button>
    </>
  );
};

export const FileTable = ({ files, selected, onToggle, onToggleAll, onDelete, onReplace, onDownload }) => {
  const allSelected = files.length > 0 && files.every((f) => selected.has(f.id));

  if (files.length === 0) {
    return (
      <div
        data-testid="empty-file-state"
        className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-16 text-center"
      >
        <GitMerge className="mb-3 h-8 w-8 text-muted-foreground/50" />
        <p className="font-display text-base font-semibold text-foreground">No files in the queue yet</p>
        <p className="mt-1 text-sm text-muted-foreground">Upload PDF or Excel files to get started.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card/40">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-left" data-testid="file-table">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wider text-muted-foreground">
              <th className="w-10 px-4 py-3">
                <Checkbox
                  data-testid="select-all-checkbox"
                  checked={allSelected}
                  onCheckedChange={(v) => onToggleAll(!!v)}
                />
              </th>
              <th className="px-3 py-3 font-semibold">File Name</th>
              <th className="px-3 py-3 font-semibold">Status</th>
              <th className="px-3 py-3 font-semibold">Password</th>
              <th className="px-3 py-3 font-semibold">Size</th>
              <th className="px-3 py-3 text-right font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {files.map((f) => {
              const Icon = f.file_type === "excel" ? Sheet : FileText;
              const iconColor = f.file_type === "excel" ? "text-emerald-400" : "text-rose-400";
              const isSel = selected.has(f.id);
              return (
                <tr
                  key={f.id}
                  data-testid={`file-row-${f.id}`}
                  className={cn(
                    "border-b border-border/60 text-sm transition-colors last:border-0 hover:bg-accent/40",
                    isSel && "bg-primary/5",
                  )}
                >
                  <td className="px-4 py-3">
                    <Checkbox
                      data-testid={`select-file-${f.id}`}
                      checked={isSel}
                      onCheckedChange={() => onToggle(f.id)}
                    />
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex items-center gap-2.5">
                      <Icon className={cn("h-4 w-4 shrink-0", iconColor)} />
                      <span className="max-w-[260px] truncate font-medium text-foreground" title={f.original_name}>
                        {f.original_name}
                      </span>
                      {f.is_merged && (
                        <span className="rounded bg-indigo-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-300">
                          MERGED
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <StatusBadge status={f.status} testid={`status-${f.id}`} />
                  </td>
                  <td className="px-3 py-3">
                    {f.matched_password ? (
                      <code className="rounded bg-muted px-2 py-0.5 text-xs font-mono-c text-foreground">
                        {f.matched_password}
                      </code>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3 font-mono-c text-xs text-muted-foreground">{fmtSize(f.size)}</td>
                  <td className="px-3 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        data-testid={`download-file-btn-${f.id}`}
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-emerald-400 disabled:opacity-30"
                        title="Download"
                        disabled={f.status === "locked" || f.status === "matched" || f.status === "error"}
                        onClick={() => onDownload(f)}
                      >
                        <Download className="h-4 w-4" />
                      </Button>
                      <ReplaceButton file={f} onReplace={onReplace} />
                      <Button
                        data-testid={`delete-file-btn-${f.id}`}
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-rose-400"
                        title="Delete"
                        onClick={() => onDelete(f)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
