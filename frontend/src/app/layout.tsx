import type { Metadata } from "next";
import "./globals.css";

import { Providers } from "@/app/providers";
import { AppShell } from "@/components/shell/AppShell";

export const metadata: Metadata = {
  title: "Research AI",
  description: "Chat, coding agent and deep research assistant backed by Qwen3.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body className="antialiased">
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
