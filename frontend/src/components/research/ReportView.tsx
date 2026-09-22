import { AlertTriangle, CheckCircle2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { ReportSections } from "@/lib/api-types";

function isReportSections(report: unknown): report is ReportSections {
  return typeof report === "object" && report !== null && "executive_summary" in report;
}

function ListSection({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{title}</h3>
      <ul className="list-disc space-y-1 pl-5 text-sm">
        {items.map((item, i) => (
          <li key={i}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function TextSection({ title, text }: { title: string; text: string }) {
  if (!text) return null;
  return (
    <div>
      <h3 className="mb-2 text-sm font-semibold text-muted-foreground">{title}</h3>
      <div className="prose prose-sm dark:prose-invert max-w-none">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </div>
  );
}

export function ReportView({ report }: { report: ReportSections | Record<string, unknown> }) {
  if (!isReportSections(report)) {
    return (
      <p className="text-sm text-muted-foreground">
        The report could not be rendered in structured form. Raw output:
        <pre className="mt-2 overflow-x-auto rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(report, null, 2)}
        </pre>
      </p>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Research Report</CardTitle>
          {report.verification && (
            <Badge variant={report.verification.approved ? "success" : "warning"}>
              {report.verification.approved ? (
                <CheckCircle2 className="size-3.5" />
              ) : (
                <AlertTriangle className="size-3.5" />
              )}
              {report.verification.approved ? "verified" : "unverified"}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <TextSection title="Executive Summary" text={report.executive_summary} />
        <TextSection title="Market Overview" text={report.market_overview} />
        <ListSection title="Key Findings" items={report.key_findings} />
        <TextSection title="Competitor Analysis" text={report.competitor_analysis} />
        <div className="grid gap-5 sm:grid-cols-2">
          <ListSection title="Opportunities" items={report.opportunities} />
          <ListSection title="Risks" items={report.risks} />
        </div>
        <ListSection title="Evidence" items={report.evidence} />

        {report.verification && !report.verification.approved && (
          <>
            <Separator />
            <div>
              <h3 className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-warning">
                <AlertTriangle className="size-3.5" /> Critic issues
              </h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {report.verification.issues.map((issue, i) => (
                  <li key={i}>{issue}</li>
                ))}
                {report.verification.missing_evidence.map((item, i) => (
                  <li key={`missing-${i}`}>Missing evidence: {item}</li>
                ))}
              </ul>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
