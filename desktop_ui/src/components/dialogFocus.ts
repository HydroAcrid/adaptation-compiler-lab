import { useLayoutEffect, useRef } from "react";

/** Restore focus only within the still-visible page that opened the dialog. */
export function useDialogFocusReturn(pageVisible: boolean) {
  const opener = useRef<HTMLElement | null>(null);
  const visible = useRef(pageVisible);
  useLayoutEffect(() => {
    visible.current = pageVisible;
  }, [pageVisible]);
  return {
    onOpenAutoFocus: () => {
      const active = document.activeElement;
      if (active instanceof HTMLElement && active !== document.body) {
        opener.current = active;
      }
    },
    onCloseAutoFocus: (event: Event) => {
      event.preventDefault();
      const target = opener.current;
      if (
        visible.current &&
        target?.isConnected &&
        !target.closest("[hidden], [inert]")
      ) {
        target.focus({ preventScroll: true });
      }
    },
  };
}
