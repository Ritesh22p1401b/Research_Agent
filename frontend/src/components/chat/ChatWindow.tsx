"use client";

import { Loader2, Send, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ChatMessageBubble } from "@/components/chat/ChatMessageBubble";
import { DocumentUploadDialog } from "@/components/documents/DocumentUploadDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useChat } from "@/hooks/useChat";
import { useChatStore } from "@/store/chat-store";

export function ChatWindow() {
  const { messages, addMessage, clear } = useChatStore();
  const chat = useChat();
  const [input, setInput] = useState("");

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || chat.isPending) return;

    const history = messages;
    addMessage({ role: "user", content: trimmed });
    setInput("");

    chat.mutate(
      { message: trimmed, history },
      {
        onSuccess: (data) => {
          addMessage({ role: "assistant", content: data.reply });
        },
        onError: (error) => {
          toast.error(error instanceof Error ? error.message : "Chat request failed");
        },
      },
    );
  };

  return (
    <Card className="flex h-[70vh] flex-col">
      <CardContent className="flex flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Send a message to chat directly with the Qwen3 model (no agents, no tools - just a raw
            completion).
          </p>
        )}
        {messages.map((message, i) => (
          <ChatMessageBubble key={i} message={message} />
        ))}
        {chat.isPending && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" /> thinking...
          </div>
        )}
      </CardContent>
      <div className="flex items-end gap-2 border-t border-border p-3">
        <DocumentUploadDialog />
        <Textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          placeholder="Ask something..."
          className="min-h-[44px] flex-1 resize-none"
        />
        <Button variant="outline" size="icon" onClick={clear} title="Clear chat">
          <Trash2 />
        </Button>
        <Button size="icon" onClick={handleSend} disabled={chat.isPending} title="Send">
          <Send />
        </Button>
      </div>
    </Card>
  );
}
