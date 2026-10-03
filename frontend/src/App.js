import { useCallback, useEffect, useMemo, useState } from "react";
import "@/App.css";
import { Toaster } from "@/components/ui/sonner";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  ShieldCheck, KeyRound, Unlock, FileArchive, GitMerge, Moon, Sun, Loader2, Sparkles, Layers,
} from "lucide-react";
import { api, getSessionId } from "@/lib/api";
import { Dropzone } from "@/components/Dropzone";
import { FileTable } from "@/components/FileTable";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "locked", label: "Locked" },
  { key: "matched", label: "Matched" },
  { key: "unlocked", label: "Unlocked" },
  { key: "error", label: "Error" },
];

function Stat({ label, value, color }) {
  return (
    <div className="flex flex-col">
      <span className="font-display text-xl font-extrabold leading-none" style={{ color }}>{value}</span>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
    </div>
  );
}

export default function App() {
  const sid = getSessionId();
  const [files, setFiles] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [passwords, setPasswords] = useState("");
  const [filter, setFilter] = useState("all");
  const [uploading, setUploading] = useState(false);
  const [matching, setMatching] = useState(false);
  const [unlocking, setUnlocking] = useState(false);
  const [dark, setDark] = useState(true);
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeName, setMergeName] = useState("merged.pdf");
  const [merging, setMerging] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
  }, [dark]);

  const refresh = useCallback(async () => {
    try {
      setFiles(await api.listFiles(sid));
    } catch (e) {
      toast.error("Failed to load files");
    }
  }, [sid]);

  useEffect(() => { refresh(); }, [refresh]);

  const stats = useMemo(() => ({
    total: files.length,
    locked: files.filter((f) => f.status === "locked").length,
    matched: files.filter((f) => f.status === "matched").length,
    unlocked: files.filter((f) => f.status === "unlocked" || f.status === "ready").length,
  }), [files]);

  const visible = useMemo(
    () => (filter === "all" ? files : files.filter((f) => f.status === filter)),
    [files, filter],
  );

  const pwList = useMemo(
    () => passwords.split(/[\n,]/).map((p) => p.trim()).filter(Boolean),
    [passwords],
  );

  const handleUpload = async (list) => {
    setUploading(true);
    try {
      await api.upload(sid, list);
      toast.success(`${list.length} file(s) uploaded`);
      await refresh();
    } catch (e) {
      toast.error("Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleMatch = async () => {
    if (pwList.length === 0) return toast.error("Enter at least one password");
    setMatching(true);
    try {
      const res = await api.match(sid, pwList);
      setFiles(res.files);
      toast.success(`${res.matched_count} file(s) matched a password`);
    } catch (e) {
      toast.error("Matching failed");
    } finally {
      setMatching(false);
    }
  };

  const handleUnlockAll = async () => {
    const ids = files.filter((f) => f.status === "matched").map((f) => f.id);
    if (ids.length === 0) return toast.error("No matched files to unlock");
    setUnlocking(true);
    try {
      const res = await api.unlock(sid, ids);
      setFiles(res.files);
      toast.success(`${res.unlocked} file(s) unlocked — no password needed anymore`);
    } catch (e) {
      toast.error("Unlock failed");
    } finally {
      setUnlocking(false);
    }
  };

  const toggle = (id) => setSelected((s) => {
    const n = new Set(s);
    n.has(id) ? n.delete(id) : n.add(id);
    return n;
  });
  const toggleAll = (on) => setSelected(on ? new Set(visible.map((f) => f.id)) : new Set());

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await api.remove(sid, deleteTarget.id);
      toast.success("File deleted");
      setSelected((s) => { const n = new Set(s); n.delete(deleteTarget.id); return n; });
      await refresh();
    } catch (e) {
      toast.error("Delete failed");
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleReplace = async (file, newFile) => {
    try {
      await api.replace(sid, file.id, newFile);
      toast.success(`Replaced "${file.original_name}"`);
      await refresh();
    } catch (e) {
      toast.error("Replace failed");
    }
  };

  const handleDownload = (f) => {
    window.open(api.downloadFileUrl(sid, f.id), "_blank");
  };

  const handleDownloadZip = () => {
    if (stats.unlocked === 0) return toast.error("No unlocked files to download");
    window.open(api.downloadZipUrl(sid), "_blank");
  };

  const handleMerge = async () => {
    const chosen = files.filter((f) => selected.has(f.id) && f.file_type === "pdf");
    if (chosen.length < 2) return toast.error("Select at least 2 unlocked PDF files");
    setMerging(true);
    try {
      await api.merge(sid, chosen.map((f) => f.id), mergeName);
      toast.success("PDFs merged successfully");
      setMergeOpen(false);
      setSelected(new Set());
      await refresh();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Merge failed");
    } finally {
      setMerging(false);
    }
  };

  const selectedPdfCount = files.filter((f) => selected.has(f.id) && f.file_type === "pdf").length;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Toaster position="top-right" richColors />

      {/* Header */}
      <header className="sticky top-0 z-30 border-b border-border bg-background/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1400px] flex-wrap items-center gap-4 px-5 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/30">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h1 className="font-display text-lg font-extrabold leading-none tracking-tight">UnlockVault</h1>
              <p className="text-[11px] text-muted-foreground">Mass PDF & Excel password unlocker</p>
            </div>
          </div>

          <div className="ml-2 hidden items-center gap-6 rounded-xl border border-border bg-card/50 px-5 py-2 md:flex">
            <Stat label="Files" value={stats.total} color="hsl(var(--foreground))" />
            <Stat label="Locked" value={stats.locked} color="#fb7185" />
            <Stat label="Matched" value={stats.matched} color="#a5b4fc" />
            <Stat label="Unlocked" value={stats.unlocked} color="#6ee7b7" />
          </div>

          <div className="ml-auto flex items-center gap-2">
            <Button
              data-testid="merge-pdf-btn"
              variant="outline"
              className="gap-2"
              onClick={() => setMergeOpen(true)}
              disabled={selectedPdfCount < 2}
            >
              <GitMerge className="h-4 w-4" /> Merge PDF
            </Button>
            <Button
              data-testid="download-zip-btn"
              className="gap-2"
              onClick={handleDownloadZip}
              disabled={stats.unlocked === 0}
            >
              <FileArchive className="h-4 w-4" /> Download ZIP
            </Button>
            <Button
              data-testid="theme-toggle-btn"
              variant="ghost"
              size="icon"
              onClick={() => setDark((d) => !d)}
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] px-5 py-8">
        {/* Upper section */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="animate-rise lg:col-span-7">
            <Dropzone onFiles={handleUpload} uploading={uploading} />
          </div>

          <div className="animate-rise rounded-2xl border border-border bg-card/40 p-5 lg:col-span-5" style={{ animationDelay: "80ms" }}>
            <div className="mb-3 flex items-center gap-2">
              <KeyRound className="h-4 w-4 text-primary" />
              <h2 className="font-display text-base font-bold">Password List</h2>
              <span className="ml-auto rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                {pwList.length} entered
              </span>
            </div>
            <Textarea
              data-testid="password-list-textarea"
              value={passwords}
              onChange={(e) => setPasswords(e.target.value)}
              placeholder={"Paste passwords — one per line or comma-separated\n\n123456\nsecret2024\ncompany@pass"}
              className="min-h-[140px] resize-none font-mono-c text-sm"
            />
            <p className="mt-2 text-xs text-muted-foreground">
              The system tries every password against each locked file and flags the matches.
            </p>
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <Button
                data-testid="match-passwords-btn"
                className="flex-1 gap-2"
                onClick={handleMatch}
                disabled={matching || stats.locked === 0}
              >
                {matching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                Match Passwords
              </Button>
              <Button
                data-testid="unlock-all-btn"
                variant="secondary"
                className="flex-1 gap-2"
                onClick={handleUnlockAll}
                disabled={unlocking || stats.matched === 0}
              >
                {unlocking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Unlock className="h-4 w-4" />}
                Unlock All ({stats.matched})
              </Button>
            </div>
          </div>
        </div>

        {/* Lower section */}
        <div className="animate-rise mt-8" style={{ animationDelay: "160ms" }}>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <Layers className="h-5 w-5 text-primary" />
              <h2 className="font-display text-xl font-bold tracking-tight">File Queue</h2>
            </div>
            <div className="ml-auto flex flex-wrap gap-1.5 rounded-xl border border-border bg-card/40 p-1">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  data-testid={`filter-${f.key}`}
                  onClick={() => setFilter(f.key)}
                  className={
                    "rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors " +
                    (filter === f.key
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground")
                  }
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          <FileTable
            files={visible}
            selected={selected}
            onToggle={toggle}
            onToggleAll={toggleAll}
            onDelete={setDeleteTarget}
            onReplace={handleReplace}
            onDownload={handleDownload}
          />
        </div>
      </main>

      {/* Merge dialog */}
      <Dialog open={mergeOpen} onOpenChange={setMergeOpen}>
        <DialogContent data-testid="merge-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Merge PDF Files</DialogTitle>
            <DialogDescription>
              Combine {selectedPdfCount} selected PDF file(s) into one document (in selection order).
              Locked PDFs must be unlocked first.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Output file name
            </label>
            <Input
              data-testid="merge-name-input"
              value={mergeName}
              onChange={(e) => setMergeName(e.target.value)}
              className="font-mono-c"
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setMergeOpen(false)}>Cancel</Button>
            <Button data-testid="confirm-merge-btn" onClick={handleMerge} disabled={merging} className="gap-2">
              {merging ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
              Merge
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(o) => !o && setDeleteTarget(null)}>
        <AlertDialogContent data-testid="delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="font-display">Delete this file?</AlertDialogTitle>
            <AlertDialogDescription>
              "{deleteTarget?.original_name}" will be removed from the queue. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              data-testid="confirm-delete-btn"
              onClick={handleDelete}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
