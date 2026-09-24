"use client";

import { Code2, Loader2, MessageSquare, Send, Trash2 } from "lucide-react";

import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { DocumentUploadDialog } from "@/components/documents/DocumentUploadDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useChatStore } from "@/store/chat-store";

export function ChatWindow() {
  const { messages, mode, draft, isPending, setMode, setDraft, send, clear } = useChatStore();

  return (
    <Card className="flex h-[70vh] flex-col">
      <div className="flex gap-1 border-b border-border p-2">
        <Button type="button" size="sm" variant={mode === "chat" ? "default" : "ghost"} onClick={() => setMode("chat")}>
          <MessageSquare /> Chat
        </Button>
        <Button
          type="button"
          size="sm"
          variant={mode === "code" ? "default" : "ghost"}
          onClick={() => setMode("code")}
          title="Coding agent: writes code, searches the web when unsure, and learns from what it finds"
        >
          <Code2 /> Coding agent
        </Button>
      </div>
      <CardContent className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.map((message, i) => (
          <ChatMessageBubble key={i} message={message} />
        ))}
        {isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />{" "}
            {mode === "code" ? "writing code (may search the web)..." : "thinking..."}
          </div>
        )}
      </CardContent>
      <div className="flex items-end gap-2 border-t border-border p-3">
        <DocumentUploadDialog />
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              send(draft);
            }
          }}
          placeholder={mode === "code" ? "Describe the code you need or paste an error..." : "Ask something..."}
          className="min-h-[44px] flex-1 resize-none"
        />
        <Button variant="outline" size="icon" onClick={clear} title="Clear chat">
          <Trash2 />
        </Button>
        <Button size="icon" onClick={() => send(draft)} disabled={isPending} title="Send">
          <Send />
        </Button>
      </div>
    </Card>
  );
}
