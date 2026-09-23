"use client";

import { Loader2, Search } from "lucide-react";
import { useState } from "react";

import { AttachedDocuments } from "@/components/documents/AttachedDocuments";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useAttachedDocuments } from "@/hooks/useAttachedDocuments";
import type { ReportDepth, ResearchMode } from "@/lib/api-types";

export type ResearchOptions = {
  documentIds: string[];
  mode: ResearchMode;
  reportDepth: ReportDepth;
};

const SELECT_CLASS =
  "h-9 rounded-md border border-border bg-card px-2.5 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function ResearchForm({
  onSubmit,
  isPending,
}: {
  onSubmit: (query: string, options: ResearchOptions) => void;
  isPending: boolean;
}) {
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<ResearchMode>("fast");
  const [reportDepth, setReportDepth] = useState<ReportDepth>("standard");
  const attached = useAttachedDocuments();

  const canSubmit = !isPending && query.trim().length >= 3;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit(query.trim(), { documentIds: attached.ids, mode, reportDepth });
      }}
      className="flex flex-col gap-3"
    >
      <Textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. Analyze the Indian EV market and identify major opportunities, risks and competitors."
        className="min-h-[72px]"
      />

      <AttachedDocuments
        documents={attached.documents}
        isUploading={attached.isUploading}
        onFiles={attached.upload}
        onRemove={attached.remove}
      />

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Research mode
          <select value={mode} onChange={(e) => setMode(e.target.value as ResearchMode)} className={SELECT_CLASS}>
            <option value="fast">Fast (parallel retrieval)</option>
            <option value="agentic">Deep (step-by-step agent)</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Word report
          <select
            value={reportDepth}
            onChange={(e) => setReportDepth(e.target.value as ReportDepth)}
            className={SELECT_CLASS}
          >
            <option value="standard">Standard (~15-25 pages)</option>
            <option value="comprehensive">Comprehensive (up to 100 pages)</option>
            <option value="none">No document</option>
          </select>
        </label>
        <Button type="submit" disabled={!canSubmit} className="ml-auto">
          {isPending ? <Loader2 className="animate-spin" /> : <Search />}
          Run research
        </Button>
      </div>
    </form>
  );
}
