"use client";

import { FileText, Loader2, PauseCircle, Plus, UploadCloud, X, XCircle } from "lucide-react";
import { type ReactNode, useState } from "react";
import { toast } from "sonner";

import { FileDropzone } from "@/components/documents/FileDropzone";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import { useDocuments, useUploadDocuments } from "@/hooks/useDocuments";
import { ACCEPTED_DOCUMENT_EXTENSIONS } from "@/lib/api-types";

export function DocumentUploadDialog({ trigger }: { trigger?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const [staged, setStaged] = useState<File[]>([]);

  const documents = useDocuments(open);
  const upload = useUploadDocuments();

  const addFiles = (files: File[]) => {
    setStaged((prev) => [...prev, ...files]);
  };

  const removeStaged = (index: number) => {
    setStaged((prev) => prev.filter((_, i) => i !== index));
  };

  const handleUpload = () => {
    if (staged.length === 0) return;
    upload.mutate(staged, {
      onSuccess: (data) => {
        if (data.queued.length > 0) {
          toast.success(
            `Added ${data.queued.length} document(s) - searchable now, indexing continues in the background`,
          );
        }
        for (const error of data.errors) {
          toast.error(error);
        }
        setStaged([]);
      },
      onError: (error) => {
        toast.error(error instanceof Error ? error.message : "Upload failed");
      },
    });
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {trigger ?? (
          <Button type="button" variant="outline" size="icon" title="Upload documents">
            <Plus />
          </Button>
        )}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Upload documents</DialogTitle>
          <DialogDescription>
            Adds files to the RAG knowledge base ({ACCEPTED_DOCUMENT_EXTENSIONS.join(", ")}). Choose files
            from your computer or drag them in.
          </DialogDescription>
        </DialogHeader>

        <FileDropzone onFiles={addFiles} disabled={upload.isPending} className="p-6">
          <UploadCloud className="size-6" />
          <span>
            <span className="font-medium text-foreground">Click to choose files</span> or drag them here
          </span>
        </FileDropzone>

        {staged.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5">
            {staged.map((file, i) => (
              <li
                key={`${file.name}-${i}`}
                className="flex items-center justify-between rounded-md bg-muted px-2.5 py-1.5 text-sm"
              >
                <span className="flex items-center gap-1.5 truncate">
                  <FileText className="size-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{file.name}</span>
                </span>
                <button
                  type="button"
                  onClick={() => removeStaged(i)}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <Button
          type="button"
          onClick={handleUpload}
          disabled={staged.length === 0 || upload.isPending}
          className="mt-3 w-full"
        >
          {upload.isPending ? <Loader2 className="animate-spin" /> : <UploadCloud />}
          Upload {staged.length > 0 ? `(${staged.length})` : ""}
        </Button>

        <Separator className="my-4" />

        <div>
          <h3 className="mb-2 text-sm font-semibold text-muted-foreground">Knowledge base documents</h3>
          {documents.isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {documents.data && documents.data.length === 0 && (
            <p className="text-sm text-muted-foreground">No documents ingested yet.</p>
          )}
          {documents.data && documents.data.length > 0 && (
            <ul className="flex max-h-40 flex-col gap-1 overflow-y-auto text-sm">
              {documents.data.map((doc) => {
                const inFlight =
                  doc.status === "queued" || doc.status === "processing" || doc.status === "indexing";
                return (
                  <li key={doc.id} className="flex items-center gap-1.5 truncate text-muted-foreground">
                    {doc.paused ? (
                      <PauseCircle className="size-3.5 shrink-0 text-warning" />
                    ) : inFlight ? (
                      <Loader2 className="size-3.5 shrink-0 animate-spin" />
                    ) : doc.status === "failed" ? (
                      <XCircle className="size-3.5 shrink-0 text-destructive" />
                    ) : (
                      <FileText className="size-3.5 shrink-0" />
                    )}
                    <span className="truncate">{doc.title}</span>
                    {inFlight && (
                      <span className="ml-auto shrink-0 text-xs italic">
                        {doc.paused
                          ? "paused for retrieval"
                          : doc.status === "queued"
                            ? "queued"
                            : `indexing ${doc.progress}%`}
                      </span>
                    )}
                    {doc.status === "failed" && (
                      <span className="ml-auto shrink-0 text-xs text-destructive">failed</span>
                    )}
                    {doc.status === "completed" && doc.category && (
                      <span className="ml-auto shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs">
                        {doc.category}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
