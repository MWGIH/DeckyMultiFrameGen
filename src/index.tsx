import { useEffect, useState } from "react";
import { staticClasses } from "@decky/ui";
import { definePlugin } from "@decky/api";
import { MdOutlineAutoAwesomeMotion } from "react-icons/md";
import { getBackends, listInstalledGames, logError, type Backend, type GameSummary } from "./api";
import { useSelectedGame } from "./hooks/useSelectedGame";
import { BackendsSection } from "./components/BackendsSection";
import { GameSection } from "./components/GameSection";
import { useHelixStatus } from "./components/HelixSRSetup";
import { useOptiStatus } from "./components/OptiScaler";
import { helixsrStatus, optiscalerStatus, type GameChoice } from "./api";
import { Content as MakoContent } from "./mako/components/Content";

const PICKED_KEY = "multifg:picked";
const SHOW_MAKO_KEY = "multifg:showMako";
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
  const [opti, setOpti] = useOptiStatus();
  const [choice, setChoice] = useState<GameChoice | null>(null);
  const [showMako, setShowMako] = useState(() => {
    try {
      return localStorage.getItem(SHOW_MAKO_KEY) === "1";
    } catch {
      return false;
    }
  });
  const toggleMako = () => {
    setShowMako(!showMako);
    try {
      localStorage.setItem(SHOW_MAKO_KEY, showMako ? "0" : "1");
    } catch {
      // just not remembered
    }
  };
  const refreshOpti = () => optiscalerStatus().then(setOpti);

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
      <GameSection
        selected={selected}
        games={games}
        backends={backends}
        helix={helix}
        opti={opti}
        onPick={pick}
        onChoice={setChoice}
      />
      {/* MAKO Decky's own controls (vendored, GPL-3.0), shown for a MAKO game or when opened from Backends */}
      {(choice === "mako" || showMako) && <MakoContent />}
      <BackendsSection
        backends={backends}
        helix={helix}
        onHelixChange={refreshHelix}
        opti={opti}
        onOptiChange={refreshOpti}
        makoShown={choice === "mako" || showMako}
        makoPinned={choice === "mako"}
        onToggleMako={toggleMako}
      />
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
