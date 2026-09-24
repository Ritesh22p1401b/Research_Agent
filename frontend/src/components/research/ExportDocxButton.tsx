"use client";

import { Download, Loader2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { exportResearchDocx } from "@/lib/api-client";
import type { ResearchResponse } from "@/lib/api-types";

/** Downloads the research result above as a Word (.docx) file - instant, no model calls. */
export function ExportDocxButton({ query, result }: { query: string; result: ResearchResponse }) {
  const [busy, setBusy] = useState(false);

  const handleClick = async () => {
    setBusy(true);
    try {
      await exportResearchDocx(query, result);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Download failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button type="button" variant="outline" size="sm" onClick={handleClick} disabled={busy}>
      {busy ? <Loader2 className="animate-spin" /> : <Download />}
      Download research (.docx)
    </Button>
  );
}
