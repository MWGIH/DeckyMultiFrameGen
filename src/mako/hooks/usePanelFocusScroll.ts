import { createContext, useContext } from "react";

/** Reapply the panel's current focus scrolling after a child changes layout. */
export const PanelFocusScrollContext = createContext<() => void>(() => {});

export function usePanelFocusScroll() {
  return useContext(PanelFocusScrollContext);
}
