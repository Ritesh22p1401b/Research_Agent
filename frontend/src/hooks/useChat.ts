import { useMutation } from "@tanstack/react-query";

import { postChat } from "@/lib/api-client";
import type { ChatMessage } from "@/lib/api-types";

export function useChat() {
  return useMutation({
    mutationFn: ({ message, history }: { message: string; history: ChatMessage[] }) =>
      postChat({ message, history }),
  });
}
