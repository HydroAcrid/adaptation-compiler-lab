import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { pageForScreen, type Page } from "./pageVisibility";
import type { Screen } from "./types";

export function usePageNavigation(firstScreen: Screen) {
  const [screen, changeScreen] = useState(firstScreen);
  const page = pageForScreen(screen);
  const scrollHost = useRef<HTMLElement | null>(null);
  const scrollPositions = useRef(new Map<Page, number>());
  const previousPage = useRef(page);

  useLayoutEffect(() => {
    const host = scrollHost.current;
    if (!host || previousPage.current === page) return;
    previousPage.current = page;
    host.scrollTop = scrollPositions.current.get(page) ?? 0;
    host.scrollLeft = 0;
    host.focus({ preventScroll: true });
  }, [page]);

  const setScreen = useCallback((destination: Screen) => {
    if (scrollHost.current) {
      scrollPositions.current.set(
        previousPage.current,
        scrollHost.current.scrollTop,
      );
    }
    changeScreen(destination);
  }, []);

  return { screen, setScreen, scrollHost };
}
