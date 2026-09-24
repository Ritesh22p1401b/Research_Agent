"use client";

import { Check, Copy } from "lucide-react";
import { Children, type ReactElement, type ReactNode, isValidElement, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { cn } from "@/lib/utils";

export function CopyButton({ text, className, label = "Copy" }: { text: string; className?: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      title={label}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // clipboard unavailable (insecure context) - nothing to do
        }
      }}
      className={cn("inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground", className)}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
      {copied ? "Copied" : label}
    </button>
  );
}

function CodeBlock({ children }: { children?: ReactNode }) {
  const child = Children.toArray(children)[0];
  if (!isValidElement(child)) return <pre>{children}</pre>;
  const el = child as ReactElement<{ className?: string; children?: ReactNode }>;
  const language = /language-([\w+#-]+)/.exec(el.props.className ?? "")?.[1] ?? "";
  const text = String(el.props.children ?? "").replace(/\n$/, "");

  return (
    <div className="not-prose my-4 overflow-hidden rounded-xl border border-border bg-[#0d0d0d] text-[#ececec]">
      <div className="flex items-center justify-between bg-[#2f2f2f] px-4 py-2 text-xs text-[#b4b4b4]">
        <span>{language || "code"}</span>
        <CopyButton text={text} className="text-[#b4b4b4] hover:text-white" />
      </div>
      <pre className="overflow-x-auto p-4 text-[13px] leading-6">
        <code>{text}</code>
      </pre>
    </div>
  );
}

export function Markdown({ children, className }: { children: string; className?: string }) {
  return (
    <div
      className={cn(
        "prose prose-neutral dark:prose-invert max-w-none text-[15px] leading-7",
        "prose-headings:font-semibold prose-headings:mt-6 prose-headings:mb-2 prose-h1:text-2xl prose-h2:text-xl prose-h3:text-lg prose-p:my-3 prose-li:my-1",
        "prose-blockquote:border-l-2 prose-blockquote:font-normal prose-blockquote:not-italic prose-blockquote:text-muted-foreground [&_blockquote_p]:before:content-none [&_blockquote_p]:after:content-none",
        "prose-a:text-foreground prose-a:underline prose-a:underline-offset-2",
        "prose-code:before:content-none prose-code:after:content-none prose-code:rounded-md prose-code:bg-muted prose-code:px-1.5 prose-code:py-0.5 prose-code:text-[13px] prose-code:font-normal",
        "prose-table:text-sm prose-th:font-semibold",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ pre: CodeBlock }}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
