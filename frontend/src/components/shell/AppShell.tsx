"use client";

import { ListChecks, Library, Menu, MessageSquare, Moon, PanelLeft, SquarePen, Sun, Trash2 } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { type ReactNode, useEffect, useState } from "react";

import { DocumentUploadDialog } from "@/components/documents/DocumentUploadDialog";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chat-store";

function SidebarItem({
  icon: Icon,
  children,
  active,
  onClick,
  href,
}: {
  icon: typeof MessageSquare;
  children: ReactNode;
  active?: boolean;
  onClick?: () => void;
  href?: string;
}) {
  const cls = cn(
    "flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors hover:bg-accent",
    active && "bg-accent",
  );
  return href ? (
    <Link href={href} onClick={onClick} className={cls}>
      <Icon className="size-[18px] shrink-0" /> {children}
    </Link>
  ) : (
    <button type="button" onClick={onClick} className={cls}>
      <Icon className="size-[18px] shrink-0" /> {children}
    </button>
  );
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const dark = mounted && resolvedTheme === "dark";
  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      title="Toggle theme"
      className="rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground"
    >
      {dark ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
    </button>
  );
}

function Sidebar({ onNavigate, onCollapse }: { onNavigate: () => void; onCollapse: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const { conversations, activeId, newChat, select, remove } = useChatStore();
  const onChat = pathname !== "/evaluate";

  const goChat = () => {
    if (pathname === "/evaluate") router.push("/");
    onNavigate();
  };

  return (
    <div className="flex h-full w-[260px] flex-col bg-sidebar p-2">
      <div className="flex items-center justify-between px-1 pb-2">
        <Link href="/" onClick={onNavigate} className="rounded-lg p-2 text-sm font-semibold">
          Research AI
        </Link>
        <button
          type="button"
          onClick={onCollapse}
          title="Close sidebar"
          className="hidden rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:block"
        >
          <PanelLeft className="size-[18px]" />
        </button>
      </div>

      <nav className="flex flex-col gap-0.5">
        <SidebarItem
          icon={SquarePen}
          onClick={() => {
            newChat();
            goChat();
          }}
        >
          New chat
        </SidebarItem>
        <SidebarItem icon={ListChecks} href="/evaluate" active={pathname === "/evaluate"} onClick={onNavigate}>
          Evaluation
        </SidebarItem>
        <DocumentUploadDialog
          trigger={
            <button type="button" className="flex w-full items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors hover:bg-accent">
              <Library className="size-[18px] shrink-0" /> Knowledge base
            </button>
          }
        />
      </nav>

      <div className="mt-4 px-3 pb-1 text-xs font-medium text-muted-foreground">Chats</div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {conversations.length === 0 && (
          <p className="px-3 py-2 text-xs text-muted-foreground">Your conversations will appear here.</p>
        )}
        {conversations.map((c) => (
          <div
            key={c.id}
            className={cn(
              "group flex items-center rounded-xl pr-1 text-sm transition-colors hover:bg-accent",
              onChat && c.id === activeId && "bg-accent",
            )}
          >
            <button
              type="button"
              onClick={() => {
                select(c.id);
                goChat();
              }}
              className="min-w-0 flex-1 truncate px-3 py-2 text-left"
              title={c.title}
            >
              {c.title}
            </button>
            <button
              type="button"
              onClick={() => remove(c.id)}
              title="Delete chat"
              className="rounded-md p-1.5 text-muted-foreground opacity-0 hover:text-foreground group-hover:opacity-100"
            >
              <Trash2 className="size-3.5" />
            </button>
          </div>
        ))}
      </div>

      <div className="flex items-center justify-between border-t border-border px-1 pt-2">
        <div className="flex items-center gap-2 px-2 text-xs text-muted-foreground">
          <span className="grid size-7 place-items-center rounded-full bg-foreground text-[11px] font-semibold text-background">
            Q3
          </span>
          Qwen3-8B
        </div>
        <ThemeToggle />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true); // desktop sidebar
  const [drawer, setDrawer] = useState(false); // mobile drawer

  return (
    <div className="flex h-dvh overflow-hidden">
      {/* desktop sidebar */}
      <aside className={cn("hidden shrink-0 overflow-hidden transition-[width] duration-200 md:block", open ? "w-[260px]" : "w-0")}>
        <Sidebar onNavigate={() => undefined} onCollapse={() => setOpen(false)} />
      </aside>

      {/* mobile drawer */}
      {drawer && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/50" onClick={() => setDrawer(false)} />
          <div className="relative h-full w-[260px]">
            <Sidebar onNavigate={() => setDrawer(false)} onCollapse={() => setDrawer(false)} />
          </div>
        </div>
      )}

      <div className="relative min-w-0 flex-1">
        {!open && (
          <button
            type="button"
            onClick={() => setOpen(true)}
            title="Open sidebar"
            className="absolute left-2 top-3 z-20 hidden rounded-lg p-2 text-muted-foreground hover:bg-accent hover:text-foreground md:block"
          >
            <PanelLeft className="size-5" />
          </button>
        )}
        <button
          type="button"
          onClick={() => setDrawer(true)}
          title="Open menu"
          className="absolute left-2 top-3 z-20 rounded-lg p-2 text-muted-foreground hover:bg-accent md:hidden"
        >
          <Menu className="size-5" />
        </button>
        <main className={cn("h-full overflow-hidden", !open && "md:pl-10")}>
          <div className="h-full pl-10 md:pl-0">{children}</div>
        </main>
      </div>
    </div>
  );
}
