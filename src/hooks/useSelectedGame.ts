import { useEffect, useState } from "react";
import { Router } from "@decky/ui";

const POLL_MS = 2000;
const LIBRARY_APP = /\/library\/app\/(\d+)/;

export type GameSource = "running" | "library" | "picked";

export type SelectedGame = { appid: string; name?: string; source: GameSource } | null;

// The game page open in Steam's library, read from the main window's router history.
function libraryAppId(): string | null {
  const router = Router as unknown as {
    WindowStore?: {
      GamepadUIMainWindowInstance?: { m_history?: { location?: { pathname?: string } } };
    };
  };
  const path = router.WindowStore?.GamepadUIMainWindowInstance?.m_history?.location?.pathname ?? "";
  const match = LIBRARY_APP.exec(path);
  return match ? match[1] : null;
}

/**
 * The game the panel is about: the running game first, then the game page open in the library,
 * then whatever the user picked from the list.
 */
export function useSelectedGame(picked: string | null): SelectedGame {
  const [detected, setDetected] = useState<SelectedGame>(null);

  useEffect(() => {
    const check = () => {
      const running = Router.MainRunningApp;
      let next: SelectedGame = null;
      if (running) {
        next = { appid: String(running.appid), name: running.display_name, source: "running" };
      } else {
        const appid = libraryAppId();
        if (appid) next = { appid, source: "library" };
      }
      setDetected((prev) =>
        prev?.appid === next?.appid && prev?.source === next?.source ? prev : next,
      );
    };
    check();
    const id = setInterval(check, POLL_MS);
    return () => clearInterval(id);
  }, []);

  if (detected) return detected;
  return picked ? { appid: picked, source: "picked" } : null;
}
