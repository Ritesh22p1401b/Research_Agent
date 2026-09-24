import { toast } from "sonner";
import { create } from "zustand";

import { postChat, postCode } from "@/lib/api-client";
import type { ChatMessage } from "@/lib/api-types";

export type ChatMode = "chat" | "code";

interface ChatState {
  messages: ChatMessage[];
  mode: ChatMode;
  draft: string;
  isPending: boolean;
  setMode: (mode: ChatMode) => void;
  setDraft: (draft: string) => void;
  send: (text: string) => void;
  clear: () => void;
}

/**
 * In memory only: the conversation (and an in-flight reply) survives switching pages, but a browser refresh
 * clears it. The request is made from the store so a reply that arrives while another page is open still lands.
 */
export const useChatStore = create<ChatState>()((set, get) => ({
  messages: [],
  mode: "chat",
  draft: "",
  isPending: false,
  setMode: (mode) => set({ mode }),
  setDraft: (draft) => set({ draft }),
  clear: () => set({ messages: [] }),
  send: (text) => {
    const message = text.trim();
    if (!message || get().isPending) return;
    const history = get().messages;
    const mode = get().mode;
    set({ messages: [...history, { role: "user", content: message }], draft: "", isPending: true });

    const request =
      mode === "code"
        ? postCode({ message, history }).then((d) => {
            const notes = [
              d.from_memory ? "*Answered from what I learned earlier.*" : "",
              d.used_web ? "*Searched the web for this" + (d.learned ? " and saved it for next time.*" : ".*") : "",
            ].filter(Boolean);
            return notes.length ? `${notes.join(" ")}\n\n${d.reply}` : d.reply;
          })
        : postChat({ message, history }).then((d) => d.reply);

    request
      .then((reply) =>
        set((s) => ({ messages: [...s.messages, { role: "assistant", content: reply }], isPending: false })),
      )
      .catch((error: unknown) => {
        set({ isPending: false });
        toast.error(error instanceof Error ? error.message : "Chat request failed");
      });
  },
}));
