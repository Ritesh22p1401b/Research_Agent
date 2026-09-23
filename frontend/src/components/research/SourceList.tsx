import { FileText, Globe, Library } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Source } from "@/lib/api-types";

export function SourceList({ sources }: { sources: Source[] }) {
  if (sources.length === 0) {
    return <p className="text-sm text-muted-foreground">No sources recorded for this run.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {sources.map((source, i) => (
        <li key={i} className="rounded-lg border border-border bg-card p-3 text-sm">
          <div className="flex items-center gap-2 font-medium">
            {source.origin === "web" ? (
              <Globe className="size-3.5 text-muted-foreground" />
            ) : source.origin === "uploaded_document" ? (
              <FileText className="size-3.5 text-muted-foreground" />
            ) : (
              <Library className="size-3.5 text-muted-foreground" />
            )}
            {source.url ? (
              <a href={source.url} target="_blank" rel="noreferrer" className="hover:underline">
                {source.title}
              </a>
            ) : (
              source.title
            )}
            <Badge variant="secondary">{source.origin.replace("_", " ")}</Badge>
          </div>
          {source.snippet && <p className="mt-1 text-muted-foreground">{source.snippet}</p>}
        </li>
      ))}
    </ul>
  );
}
