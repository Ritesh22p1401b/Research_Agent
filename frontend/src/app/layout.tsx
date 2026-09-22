import type { Metadata } from "next";
import "./globals.css";

import { Header } from "@/components/layout/Header";
import { Providers } from "@/app/providers";

export const metadata: Metadata = {
  title: "Research Intelligence Platform",
  description: "Multi-agent RAG research assistant backed by Qwen3.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <Providers>
          <Header />
          <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
