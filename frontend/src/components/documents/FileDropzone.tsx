"use client";

import { type ReactNode, useId, useState } from "react";
import { toast } from "sonner";

import { ACCEPTED_DOCUMENT_EXTENSIONS } from "@/lib/api-types";
import { cn } from "@/lib/utils";

const ACCEPT_ATTR = ACCEPTED_DOCUMENT_EXTENSIONS.join(",");

function isAccepted(file: File): boolean {
  const name = file.name.toLowerCase();
  return ACCEPTED_DOCUMENT_EXTENSIONS.some((ext) => name.endsWith(ext));
}

/**
 * One control that supports BOTH ways of adding files:
 *  - click  -> the browser's native file-picker window. This is a <label> wrapping a visually-hidden
 *              <input type="file">, so the browser opens the dialog itself (no programmatic .click(),
 *              which some browsers/dialog focus-traps swallow).
 *  - drag & drop onto the same area.
 */
export function FileDropzone({
  onFiles,
  disabled = false,
  className,
  children,
}: {
  onFiles: (files: File[]) => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const inputId = useId();
  const [dragging, setDragging] = useState(false);

  const handle = (incoming: File[]) => {
    if (incoming.length === 0) return;
    const accepted = incoming.filter(isAccepted);
    const rejected = incoming.filter((f) => !isAccepted(f));
    if (rejected.length > 0) {
      toast.error(`Unsupported file type: ${rejected.map((f) => f.name).join(", ")}`);
    }
    if (accepted.length > 0) onFiles(accepted);
  };

  return (
    <label
      htmlFor={inputId}
      onDragEnter={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "copy";
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!disabled) handle(Array.from(e.dataTransfer.files));
      }}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border p-4 text-center text-sm text-muted-foreground transition-colors focus-within:ring-2 focus-within:ring-ring hover:border-primary hover:text-foreground",
        dragging && "border-primary bg-accent text-foreground",
        disabled && "pointer-events-none opacity-50",
        className,
      )}
    >
      <input
        id={inputId}
        type="file"
        multiple
        accept={ACCEPT_ATTR}
        disabled={disabled}
        className="sr-only"
        onChange={(e) => {
          handle(Array.from(e.target.files ?? []));
          e.target.value = ""; // allow picking the same file again
        }}
      />
      {children}
    </label>
  );
}

export { ACCEPT_ATTR };
