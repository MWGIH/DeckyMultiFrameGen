import { useEffect, useState } from "react";
import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { MdOutlineAutoAwesomeMotion } from "react-icons/md";
import { getBackends, listInstalledGames, logError, type Backend, type GameSummary } from "./api";
import { useSelectedGame } from "./hooks/useSelectedGame";
import { BackendsSection } from "./components/BackendsSection";
import { GameSection } from "./components/GameSection";
import { useHelixStatus } from "./components/HelixSRSetup";
import { helixsrStatus } from "./api";

const PICKED_KEY = "multifg:picked";
const BACKEND_POLL_MS = 5000;

function readPicked(): string | null {
  try {
    return localStorage.getItem(PICKED_KEY);
  } catch {
    return null;
  }
}

function Content() {
  const [backends, setBackends] = useState<Backend[] | null>(null);
  const [games, setGames] = useState<GameSummary[]>([]);
  const [picked, setPicked] = useState<string | null>(readPicked);
  const selected = useSelectedGame(picked);
  const [helix, setHelix] = useHelixStatus();
  const refreshHelix = () => helixsrStatus().then(setHelix);

  useEffect(() => {
    const load = () =>
      getBackends()
        .then(setBackends)
        .catch((e) => logError(`get_backends: ${e}`));
    load();
    const id = setInterval(load, BACKEND_POLL_MS);
    listInstalledGames()
      .then((r) => setGames(r.games))
      .catch((e) => logError(`list_installed_games: ${e}`));
    return () => clearInterval(id);
  }, []);

  const pick = (appid: string) => {
    setPicked(appid);
    try {
      localStorage.setItem(PICKED_KEY, appid);
    } catch {
      // the pick just isn't remembered
    }
  };

  return (
    <>
      <GameSection selected={selected} games={games} backends={backends} helix={helix} onPick={pick} />
      <BackendsSection backends={backends} helix={helix} onHelixChange={refreshHelix} />
    </>
  );
}

export default definePlugin(() => ({
  name: "Decky MultiFrameGen",
  titleView: <div className={staticClasses.Title}>MultiFrameGen</div>,
  alwaysRender: true,
  content: <Content />,
  icon: <MdOutlineAutoAwesomeMotion />,
}));
