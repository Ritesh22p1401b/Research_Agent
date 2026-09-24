import { toast } from "sonner";
import { create } from "zustand";

import { postCode, streamChat } from "@/lib/api-client";
import type { ChatMessage, ResearchResponse } from "@/lib/api-types";
import { type ProgressEvent, startResearchStream } from "@/lib/research-stream";
import { useResearchStore } from "@/store/research-store";

export type ChatMode = "chat" | "code" | "research";

export interface ResearchRun {
  query: string;
  status: "running" | "completed" | "failed";
  progress: ProgressEvent[];
  result: ResearchResponse | null;
  error: string | null;
  startedAt: number;
  /** Word-report jobs started for this run, by size (overview / standard / comprehensive). */
  jobs: Record<string, string>;
}

export interface UiMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  note?: string;
  research?: ResearchRun;
}

export interface Conversation {
  id: string;
  title: string;
  messages: UiMessage[];
}

interface ChatState {
  conversations: Conversation[];
  activeId: string | null;
  mode: ChatMode;
  researchReturn: ChatMode;
  draft: string;
  pending: Record<string, boolean>;
  setMode: (mode: ChatMode) => void;
  setResearch: (on: boolean) => void;
  setReportJob: (messageId: string, size: string, jobId: string) => void;
  setDraft: (draft: string) => void;
  newChat: () => void;
  select: (id: string) => void;
  remove: (id: string) => void;
  send: (text: string) => void;
  stop: () => void;
  regenerate: () => void;
}

const stoppers = new Map<string, () => void>();
const uid = () => crypto.randomUUID();

function historyOf(messages: UiMessage[]): ChatMessage[] {
  return messages.filter((m) => m.content.trim()).map((m) => ({ role: m.role, content: m.content }));
}

function summaryText(result: ResearchResponse): string {
  const report = result.report as { executive_summary?: unknown };
  return typeof report.executive_summary === "string" ? report.executive_summary : "";
}

/**
 * All conversations live here, in memory only: they survive switching between pages (and replies that arrive
 * while another page is open still land), but a browser refresh clears everything.
 */
export const useChatStore = create<ChatState>()((set, get) => ({
  conversations: [],
  activeId: null,
  mode: "chat",
  researchReturn: "chat",
  draft: "",
  pending: {},

  setMode: (mode) => set({ mode }),
  // "Research" is a tool switched on from the + menu; switching it off returns to the previous mode.
  setResearch: (on) =>
    set((s) =>
      on
        ? { mode: "research", researchReturn: s.mode === "research" ? s.researchReturn : s.mode }
        : { mode: s.researchReturn === "research" ? "chat" : s.researchReturn },
    ),
  setReportJob: (messageId, size, jobId) =>
    set((s) => ({
      conversations: s.conversations.map((c) => ({
        ...c,
        messages: c.messages.map((m) =>
          m.id === messageId && m.research ? { ...m, research: { ...m.research, jobs: { ...m.research.jobs, [size]: jobId } } } : m,
        ),
      })),
    })),
  setDraft: (draft) => set({ draft }),
  newChat: () => set({ activeId: null, draft: "" }),
  select: (id) => set({ activeId: id }),

  remove: (id) => {
    stoppers.get(id)?.();
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      activeId: s.activeId === id ? null : s.activeId,
    }));
  },

  stop: () => {
    const id = get().activeId;
    if (id) stoppers.get(id)?.();
  },

  regenerate: () => {
    const { activeId, conversations } = get();
    const conv = conversations.find((c) => c.id === activeId);
    if (!conv || get().pending[conv.id]) return;
    const lastUser = [...conv.messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;
    const index = conv.messages.findIndex((m) => m.id === lastUser.id);
    set((s) => ({
      conversations: s.conversations.map((c) => (c.id === conv.id ? { ...c, messages: c.messages.slice(0, index) } : c)),
    }));
    get().send(lastUser.content);
  },

  send: (text) => {
    const message = text.trim();
    if (!message) return;

    let mode = get().mode;
    if (useResearchStore.getState().attached.length > 0 && mode !== "research") {
      mode = "research";
      set({ mode });
      toast.info("Using Deep research so the answer is grounded in your attached documents");
    }

    let convId = get().activeId;
    let conv = get().conversations.find((c) => c.id === convId);
    if (!conv) {
      const created: Conversation = { id: uid(), title: message.slice(0, 48), messages: [] };
      conv = created;
      convId = created.id;
      set((s) => ({ conversations: [created, ...s.conversations], activeId: created.id }));
    }
    const id = conv.id;
    if (get().pending[id]) return;

    const history = historyOf(conv.messages);
    const userMsg: UiMessage = { id: uid(), role: "user", content: message };
    const botMsg: UiMessage = {
      id: uid(),
      role: "assistant",
      content: "",
      research:
        mode === "research"
          ? { query: message, status: "running", progress: [], result: null, error: null, startedAt: Date.now(), jobs: {} }
          : undefined,
    };

    const patchConv = (fn: (c: Conversation) => Conversation) =>
      set((s) => ({ conversations: s.conversations.map((c) => (c.id === id ? fn(c) : c)) }));
    const patchBot = (fn: (m: UiMessage) => UiMessage) =>
      patchConv((c) => ({ ...c, messages: c.messages.map((m) => (m.id === botMsg.id ? fn(m) : m)) }));

    patchConv((c) => ({ ...c, messages: [...c.messages, userMsg, botMsg] }));
    set((s) => ({ draft: "", pending: { ...s.pending, [id]: true } }));

    let done = false;
    const finish = (after?: () => void) => {
      if (done) return;
      done = true;
      stoppers.delete(id);
      after?.();
      set((s) => {
        const next = { ...s.pending };
        delete next[id];
        return { pending: next };
      });
    };
    const fail = (error: unknown, fallback: string) => {
      const text = error instanceof Error ? error.message : fallback;
      finish(() => patchBot((m) => ({ ...m, content: m.content || `⚠️ ${text}` })));
      toast.error(text);
    };

    if (mode === "chat") {
      const controller = new AbortController();
      stoppers.set(id, () => {
        controller.abort();
        finish();
      });
      streamChat(
        { message, history },
        (delta) => patchBot((m) => ({ ...m, content: m.content + delta })),
        controller.signal,
      )
        .then(() => finish())
        .catch((error: unknown) => {
          if (controller.signal.aborted) return;
          fail(error, "Chat request failed");
        });
      return;
    }

    if (mode === "code") {
      stoppers.set(id, () => finish(() => patchBot((m) => ({ ...m, content: m.content || "*Stopped.*" }))));
      postCode({ message, history })
        .then((d) => {
          if (done) return;
          const notes = [
            d.from_memory ? "Answered from what I learned earlier" : "",
            d.used_web ? (d.learned ? "Searched the web and saved it for next time" : "Searched the web") : "",
          ].filter(Boolean);
          finish(() => patchBot((m) => ({ ...m, content: d.reply, note: notes.join(" · ") || undefined })));
        })
        .catch((error: unknown) => {
          if (!done) fail(error, "Coding agent request failed");
        });
      return;
    }

    // Deep research
    const options = useResearchStore.getState();
    const documentIds = options.attached.map((a) => a.id);
    const updateRun = (fn: (r: ResearchRun) => ResearchRun) =>
      patchBot((m) => (m.research ? { ...m, research: fn(m.research) } : m));
    const close = startResearchStream(
      message,
      { documentIds, mode: options.mode, reportDepth: "none" },
      {
        onProgress: (event) => updateRun((r) => ({ ...r, progress: [...r.progress, event] })),
        onDone: (result) => {
          const ok = result.status === "completed";
          finish(() =>
            patchBot((m) => ({
              ...m,
              content: summaryText(result),
              research: m.research
                ? { ...m.research, status: ok ? "completed" : "failed", result, error: ok ? null : result.error }
                : m.research,
            })),
          );
          if (!ok) toast.error(result.error ?? "Research failed");
        },
        onError: (msg) => {
          finish(() => updateRun((r) => ({ ...r, status: "failed", error: msg })));
          toast.error(msg);
        },
      },
    );
    stoppers.set(id, () => {
      close();
      finish(() => updateRun((r) => ({ ...r, status: "failed", error: "Stopped" })));
    });
    useResearchStore.getState().setAttached(() => []);
  },
}));
