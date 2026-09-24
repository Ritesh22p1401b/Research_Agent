"use client";

import { ArrowUp, CheckCircle2, FileText, Loader2, Microscope, PauseCircle, Paperclip, Plus, Square, X, XCircle } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { toast } from "sonner";

import { ACCEPT_ATTR, isAccepted } from "@/components/documents/FileDropzone";
import { type AttachedDocument, useAttachedDocuments } from "@/hooks/useAttachedDocuments";
import type { ResearchMode } from "@/lib/api-types";
import { cn } from "@/lib/utils";
import { type ChatMode, useChatStore } from "@/store/chat-store";
import { useResearchStore } from "@/store/research-store";

const PLACEHOLDERS: Record<ChatMode, string> = {
  chat: "Message the assistant",
  code: "Describe the code you need, or paste an error",
  research: "Ask anything to research",
};

const PILL =
  "h-8 rounded-full border border-border bg-transparent px-3 text-xs text-muted-foreground hover:bg-accent focus-visible:outline-none";

function DocChip({ doc, onRemove }: { doc: AttachedDocument; onRemove: () => void }) {
  const inFlight = doc.status === "queued" || doc.status === "processing" || doc.status === "indexing";
  return (
    <div className="flex items-center gap-2 rounded-xl bg-background/60 py-1.5 pl-2.5 pr-1.5 text-xs">
      <FileText className="size-4 shrink-0 text-muted-foreground" />
      <span className="max-w-[10rem] truncate font-medium">{doc.filename}</span>
      <span className="flex items-center gap-1 text-muted-foreground">
        {doc.status === "failed" ? (
          <>
            <XCircle className="size-3.5 text-destructive" /> failed
          </>
        ) : doc.paused ? (
          <>
            <PauseCircle className="size-3.5 text-warning" /> paused
          </>
        ) : inFlight ? (
          <>
            <Loader2 className="size-3.5 animate-spin" /> {doc.status === "queued" ? "queued" : `${doc.progress}%`}
          </>
        ) : (
          <>
            <CheckCircle2 className="size-3.5 text-success" /> indexed
          </>
        )}
      </span>
      <button type="button" onClick={onRemove} className="rounded-full p-1 hover:bg-accent" title="Remove">
        <X className="size-3.5" />
      </button>
    </div>
  );
}

export function Composer({ className }: { className?: string }) {
  const { mode, draft, setDraft, send, stop, pending, activeId } = useChatStore();
  const { mode: researchMode, setOptions } = useResearchStore();
  const setResearch = useChatStore((st) => st.setResearch);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const attached = useAttachedDocuments();
  const inputId = useId();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [dragging, setDragging] = useState(false);

  const busy = !!activeId && !!pending[activeId];

  // auto-grow like ChatGPT
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [draft]);

  const addFiles = (files: File[]) => {
    const ok = files.filter(isAccepted);
    const bad = files.filter((f) => !isAccepted(f));
    if (bad.length) toast.error(`Unsupported file type: ${bad.map((f) => f.name).join(", ")}`);
    if (ok.length) attached.upload(ok);
  };

  const canSend = draft.trim().length > 0 && !busy;

  useEffect(() => {
    if (!menuOpen) return;
    const close = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menuOpen]);

  return (
    <div
      className={cn(
        "rounded-[28px] border border-border bg-composer px-3 pb-2.5 pt-3 shadow-sm transition-colors",
        dragging && "border-foreground/40 bg-accent",
        className,
      )}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        addFiles(Array.from(e.dataTransfer.files));
      }}
    >
      {(attached.documents.length > 0 || attached.isUploading) && (
        <div className="mb-2 flex flex-wrap gap-2 px-1">
          {attached.documents.map((doc) => (
            <DocChip key={doc.id} doc={doc} onRemove={() => attached.remove(doc.id)} />
          ))}
          {attached.isUploading && (
            <div className="flex items-center gap-2 rounded-xl bg-background/60 px-3 py-1.5 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" /> uploading...
            </div>
          )}
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={draft}
        rows={1}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            if (canSend) send(draft);
          }
        }}
        placeholder={PLACEHOLDERS[mode]}
        className="block max-h-[220px] min-h-[28px] w-full resize-none bg-transparent px-2 text-[15px] leading-7 outline-none placeholder:text-muted-foreground"
      />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        {/* The input lives outside the menu so the native file window still opens after the menu closes. */}
        <input
          id={inputId}
          type="file"
          multiple
          accept={ACCEPT_ATTR}
          className="sr-only"
          // Close the menu only once the browser has activated the input (unmounting the label on click would cancel it).
          onClick={() => setMenuOpen(false)}
          onChange={(e) => {
            addFiles(Array.from(e.target.files ?? []));
            e.target.value = "";
          }}
        />

        <div ref={menuRef} className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            title="Add files and more"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            className={cn(
              "inline-flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
              menuOpen && "bg-accent text-foreground",
            )}
          >
            <Plus className={cn("size-5 transition-transform", menuOpen && "rotate-45")} />
          </button>

          {menuOpen && (
            <div
              role="menu"
              className="absolute bottom-full left-0 z-30 mb-2 w-72 rounded-2xl border border-border bg-card p-1.5 shadow-xl"
            >
              {/* <label> for the hidden input above: the browser itself opens the native file window */}
              <label
                htmlFor={inputId}
                role="menuitem"
                className="flex cursor-pointer items-start gap-3 rounded-xl px-3 py-2.5 hover:bg-accent"
              >
                <Paperclip className="mt-0.5 size-5 shrink-0" />
                <span>
                  <span className="block text-sm">Add files</span>
                  <span className="block text-xs text-muted-foreground">Upload PDF, DOCX, TXT, MD, CSV, JSON or HTML</span>
                </span>
              </label>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setResearch(true);
                  setMenuOpen(false);
                  textareaRef.current?.focus();
                }}
                className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-accent"
              >
                <Microscope className="mt-0.5 size-5 shrink-0" />
                <span>
                  <span className="block text-sm">Research</span>
                  <span className="block text-xs text-muted-foreground">
                    Search the web and your knowledge base, then download a Word report
                  </span>
                </span>
              </button>
            </div>
          )}
        </div>

        {mode === "research" && (
          <>
            <button
              type="button"
              onClick={() => setResearch(false)}
              title="Turn research off"
              className="inline-flex h-8 items-center gap-1.5 rounded-full bg-accent px-3 text-sm text-sky-400 hover:opacity-80"
            >
              <Microscope className="size-4" /> Research <X className="size-3.5" />
            </button>
            <select
              value={researchMode}
              onChange={(e) => setOptions({ mode: e.target.value as ResearchMode })}
              className={PILL}
              title="Research mode"
            >
              <option value="fast">Fast</option>
              <option value="agentic">Deep (step-by-step)</option>
            </select>
          </>
        )}

        <div className="ml-auto">
          {busy ? (
            <button
              type="button"
              onClick={stop}
              title="Stop"
              className="inline-flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground"
            >
              <Square className="size-3.5 fill-current" />
            </button>
          ) : (
            <button
              type="button"
              onClick={() => canSend && send(draft)}
              disabled={!canSend}
              title="Send message"
              className="inline-flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground transition-opacity disabled:opacity-30"
            >
              <ArrowUp className="size-5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
