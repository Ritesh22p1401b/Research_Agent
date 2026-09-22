import { Sparkles } from "lucide-react";

import { HealthBadge } from "@/components/layout/HealthBadge";
import { NavLink } from "@/components/layout/NavLink";

export function Header() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <div className="flex items-center gap-2 font-semibold">
          <Sparkles className="size-4 text-primary" />
          Research Intelligence Platform
        </div>
        <nav className="flex items-center gap-1">
          <NavLink href="/chat">Chat</NavLink>
          <NavLink href="/research">Research</NavLink>
          <NavLink href="/evaluate">Evaluation</NavLink>
        </nav>
        <HealthBadge />
      </div>
    </header>
  );
}
