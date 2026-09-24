import { create } from "zustand";

import type { ResearchMode } from "@/lib/api-types";

/**
 * Research composer options + the documents attached to the next message. In memory only: kept across
 * page switches, cleared by a browser refresh. (The research run itself lives in the chat message.)
 */
interface ResearchOptionsState {
  mode: ResearchMode;
  attached: { id: string; filename: string }[];
  setOptions: (patch: Partial<Pick<ResearchOptionsState, "mode">>) => void;
  setAttached: (updater: (prev: { id: string; filename: string }[]) => { id: string; filename: string }[]) => void;
}

export const useResearchStore = create<ResearchOptionsState>()((set) => ({
  mode: "fast",
  attached: [],
  setOptions: (patch) => set(patch),
  setAttached: (updater) => set((s) => ({ attached: updater(s.attached) })),
}));
