"use client";

import { RefreshCw } from "lucide-react";

import { CopyButton, Markdown } from "@/components/chat/Markdown";
import { ResearchMessage } from "@/components/chat/ResearchMessage";
import type { UiMessage } from "@/store/chat-store";

export function MessageView({
  message,
  query,
  isLast,
  busy,
  onRegenerate,
}: {
  message: UiMessage;
  query: string;
  isLast: boolean;
  busy: boolean;
  onRegenerate: () => void;
}) {
  if (message.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-3xl bg-muted px-5 py-2.5 text-[15px] leading-7 sm:max-w-[75%]">
          {message.content}
        </div>
      </div>
    );
  }

  const waiting = busy && isLast && !message.content && !message.research;

  return (
    <div className="group">
      {message.note && <div className="mb-2 text-xs italic text-muted-foreground">{message.note}</div>}

      {message.research ? (
        <ResearchMessage run={message.research} query={query} messageId={message.id} />
      ) : waiting ? (
        <span className="typing-dot mt-2" aria-label="Thinking" />
      ) : (
        <Markdown>{message.content}</Markdown>
      )}

      {!waiting && message.content && !(busy && isLast) && (
        <div className="mt-2 flex items-center gap-3 opacity-70 transition-opacity group-hover:opacity-100">
          <CopyButton text={message.content} />
          {isLast && (
            <button
              type="button"
              onClick={onRegenerate}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            >
              <RefreshCw className="size-3.5" /> Regenerate
            </button>
          )}
        </div>
      )}
    </div>
  );
}
