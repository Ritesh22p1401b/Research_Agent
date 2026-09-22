import Link from "next/link";
import { FileSearch, ListChecks, MessageSquare } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const links = [
  {
    href: "/chat",
    icon: MessageSquare,
    title: "Chat",
    description: "Direct chat completion against the Qwen3 endpoint.",
  },
  {
    href: "/research",
    icon: FileSearch,
    title: "Research",
    description: "Run the full Research → Analysis → Critic → Report agent pipeline.",
  },
  {
    href: "/evaluate",
    icon: ListChecks,
    title: "Evaluation",
    description: "Run the golden evaluation dataset and inspect metrics.",
  },
];

export default function Home() {
  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {links.map(({ href, icon: Icon, title, description }) => (
        <Link key={href} href={href}>
          <Card className="h-full transition-colors hover:border-primary">
            <CardHeader>
              <Icon className="mb-2 size-5 text-primary" />
              <CardTitle>{title}</CardTitle>
              <CardDescription>{description}</CardDescription>
            </CardHeader>
          </Card>
        </Link>
      ))}
    </div>
  );
}
