"use client";

import { Loader2, Search } from "lucide-react";
import { useState } from "react";

import { DocumentUploadDialog } from "@/components/documents/DocumentUploadDialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ResearchForm({
  onSubmit,
  isPending,
}: {
  onSubmit: (query: string) => void;
  isPending: boolean;
}) {
  const [query, setQuery] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (query.trim().length >= 3) onSubmit(query.trim());
      }}
      className="flex flex-col gap-3 sm:flex-row sm:items-end"
    >
      <DocumentUploadDialog />
      <Textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="e.g. Analyze the Indian EV market and identify major opportunities, risks and competitors."
        className="min-h-[60px] flex-1"
      />
      <Button type="submit" disabled={isPending || query.trim().length < 3} className="sm:self-end">
        {isPending ? <Loader2 className="animate-spin" /> : <Search />}
        Run research
      </Button>
    </form>
  );
}
