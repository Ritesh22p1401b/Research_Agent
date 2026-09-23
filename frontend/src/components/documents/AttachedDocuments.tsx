"use client";

import { CheckCircle2, FileText, Loader2, PauseCircle, UploadCloud, X, XCircle } from "lucide-react";

import { FileDropzone } from "@/components/documents/FileDropzone";
import type { AttachedDocument } from "@/hooks/useAttachedDocuments";

function StatusLine({ doc }: { doc: AttachedDocument }) {
  if (doc.status === "failed") {
    return (
      <span className="flex items-center gap-1 text-destructive">
        <XCircle className="size-3.5" /> indexing failed
      </span>
    );
  }
  if (doc.status === "completed") {
    return (
      <span className="flex items-center gap-1 text-success">
        <CheckCircle2 className="size-3.5" /> in knowledge base
      </span>
    );
  }
  if (doc.paused) {
    return (
      <span className="flex items-center gap-1 text-warning">
        <PauseCircle className="size-3.5" /> indexing paused - the agent is reading the knowledge base
      </span>
    );
  }
  return (
    <span className="flex items-center gap-1 text-muted-foreground">
      <Loader2 className="size-3.5 animate-spin" />
      {doc.status === "queued" ? "queued for indexing" : `indexing ${doc.progress}%`}
    </span>
  );
}

export function AttachedDocuments({
  documents,
  isUploading,
  onFiles,
  onRemove,
}: {
  documents: AttachedDocument[];
  isUploading: boolean;
  onFiles: (files: File[]) => void;
  onRemove: (id: string) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <FileDropzone onFiles={onFiles} disabled={isUploading}>
        {isUploading ? <Loader2 className="size-5 animate-spin" /> : <UploadCloud className="size-5" />}
        <span>
          <span className="font-medium text-foreground">Click to choose files</span> or drag them here
        </span>
        <span className="text-xs">
          PDF, DOCX, TXT, Markdown, CSV, JSON, HTML - the research will also cover and go beyond these documents
        </span>
      </FileDropzone>

      {documents.length > 0 && (
        <ul className="flex flex-col gap-1.5">
          {documents.map((doc) => (
            <li
              key={doc.id}
              className="flex items-center justify-between gap-3 rounded-md bg-muted px-2.5 py-1.5 text-sm"
            >
              <span className="flex min-w-0 items-center gap-1.5">
                <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">{doc.filename}</span>
              </span>
              <span className="flex shrink-0 items-center gap-3 text-xs">
                <StatusLine doc={doc} />
                <button
                  type="button"
                  onClick={() => onRemove(doc.id)}
                  title="Remove from this research"
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
