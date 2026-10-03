import { useCallback, useRef, useState } from "react";
import { UploadCloud, FileText, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const ACCEPT = ".pdf,.xlsx,.xls,.xlsm,.xlsb";

export const Dropzone = ({ onFiles, uploading }) => {
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const handleDrop = useCallback(
    (e) => {
      e.preventDefault();
      setDrag(false);
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length) onFiles(files);
    },
    [onFiles],
  );

  return (
    <div
      data-testid="file-upload-dropzone"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={handleDrop}
      className={cn(
        "group relative flex cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed p-10 text-center transition-colors duration-200",
        drag
          ? "border-primary bg-primary/10"
          : "border-border bg-card/40 hover:border-primary/60 hover:bg-card/70",
      )}
    >
      <input
        ref={inputRef}
        data-testid="file-upload-input"
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          if (files.length) onFiles(files);
          e.target.value = "";
        }}
      />
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/15 text-primary transition-transform duration-200 group-hover:scale-110">
        {uploading ? <Loader2 className="h-7 w-7 animate-spin" /> : <UploadCloud className="h-7 w-7" />}
      </div>
      <p className="font-display text-lg font-bold text-foreground">
        {uploading ? "Uploading files…" : "Drop PDF & Excel files here"}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        or <span className="font-semibold text-primary">browse</span> to select — upload in bulk
      </p>
      <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
        <FileText className="h-3.5 w-3.5" /> .pdf .xlsx .xls .xlsm
      </div>
    </div>
  );
};
