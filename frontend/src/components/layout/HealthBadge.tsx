"use client";

import { useHealth } from "@/hooks/useHealth";
import { Badge } from "@/components/ui/badge";

export function HealthBadge() {
  const { data, isLoading, isError } = useHealth();

  if (isLoading) {
    return <Badge variant="secondary">checking...</Badge>;
  }
  if (isError || !data) {
    return <Badge variant="destructive">backend unreachable</Badge>;
  }

  const variant = data.status === "ok" ? "success" : data.status === "degraded" ? "warning" : "destructive";
  return (
    <Badge variant={variant} title={`LLM: ${data.llm}`}>
      llm: {data.llm}
    </Badge>
  );
}
