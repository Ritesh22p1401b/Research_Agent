"use client";

import { Check, ChevronDown, Code2, MessageSquare, Microscope } from "lucide-react";
import type { ComponentType } from "react";
import { useEffect, useRef, useState } from "react";

import { Composer } from "@/components/chat/Composer";
import { MessageView } from "@/components/chat/MessageView";
import { HealthBadge } from "@/components/layout/HealthBadge";
import { cn } from "@/lib/utils";
import { type ChatMode, useChatStore } from "@/store/chat-store";

const RESEARCH = { id: "research" as ChatMode, label: "Research", icon: Microscope };

const MODES: { id: ChatMode; label: string; hint: string; icon: ComponentType<{ className?: string }> }[] = [
  { id: "chat", label: "Chat", hint: "Talk directly with Qwen3", icon: MessageSquare },
  { id: "code", label: "Coding agent", hint: "Writes code, searches the web when unsure, learns", icon: Code2 },
];

const SUGGESTIONS: Record<ChatMode, string[]> = {
  chat: ["Explain how retrieval-augmented generation works", "Give me a plan to learn system design in 4 weeks"],
  code: ["Write a Python script that renames photos by their EXIF date", "Explain and fix: TypeError: 'NoneType' object is not subscriptable"],
  research: [
    "Analyze the Indian EV market: opportunities, risks and competitors",
    "Compare the top cloud providers for a startup in 2025",
  ],
};

function ModeMenu() {
  const { mode, setMode } = useChatStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const current = mode === "research" ? RESEARCH : (MODES.find((m) => m.id === mode) ?? MODES[0]!);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-lg font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        {current.label} <ChevronDown className="size-4" />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-30 mt-1 w-72 rounded-2xl border border-border bg-card p-1.5 shadow-xl">
          {MODES.map(({ id, label, hint, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => {
                setMode(id);
                setOpen(false);
              }}
              className="flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-accent"
            >
              <Icon className="mt-0.5 size-5 shrink-0" />
              <span className="flex-1">
                <span className="block text-sm">{label}</span>
                <span className="block text-xs text-muted-foreground">{hint}</span>
              </span>
              {mode === id && <Check className="mt-0.5 size-4" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ChatScreen({ presetMode }: { presetMode?: ChatMode }) {
  const { conversations, activeId, mode, pending, setDraft, regenerate } = useChatStore();
  const setMode = useChatStore((s) => s.setMode);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (presetMode) setMode(presetMode);
  }, [presetMode, setMode]);

  const conversation = conversations.find((c) => c.id === activeId);
  const messages = conversation?.messages ?? [];
  const busy = !!activeId && !!pending[activeId];
  const lastLength = messages[messages.length - 1]?.content.length ?? 0;
  const progressCount = messages[messages.length - 1]?.research?.progress.length ?? 0;

  // keep the newest content in view while streaming
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight });
  }, [messages.length, lastLength, progressCount, activeId]);

  const empty = messages.length === 0;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="flex shrink-0 items-center justify-between px-3 py-2">
        <ModeMenu />
        <HealthBadge />
      </header>

      {empty ? (
        <div className="flex flex-1 flex-col items-center justify-center px-4 pb-24">
          <h1 className="mb-8 text-center text-3xl font-medium sm:text-4xl">What are you working on?</h1>
          <Composer className="w-full max-w-3xl" />
          <div className="mt-5 flex max-w-3xl flex-wrap justify-center gap-2">
            {SUGGESTIONS[mode].map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setDraft(s)}
                className="rounded-full border border-border px-4 py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <>
          <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 px-4 py-6">
              {messages.map((m, i) => {
                const prevUser = [...messages.slice(0, i)].reverse().find((x) => x.role === "user");
                return (
                  <MessageView
                    key={m.id}
                    message={m}
                    query={m.research?.query ?? prevUser?.content ?? ""}
                    isLast={i === messages.length - 1}
                    busy={busy}
                    onRegenerate={regenerate}
                  />
                );
              })}
            </div>
          </div>
          <div className="shrink-0 px-4 pb-3 pt-1">
            <div className="mx-auto w-full max-w-3xl">
              <Composer />
              <p className={cn("mt-2 text-center text-xs text-muted-foreground")}>
                Answers can be wrong - check important information and the sources.
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
