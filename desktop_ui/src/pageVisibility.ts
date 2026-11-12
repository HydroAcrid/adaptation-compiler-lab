import { createContext, useContext } from "react";

import type { Screen } from "./types";

export type Page = Exclude<Screen, "onboarding" | "suggestion" | "tray">;

export function pageForScreen(screen: Screen): Page {
  switch (screen) {
    case "onboarding":
    case "suggestion":
    case "tray":
      return "today";
    default:
      return screen;
  }
}

export const PageVisibility = createContext(true);

export function usePageVisibility(): boolean {
  return useContext(PageVisibility);
}
