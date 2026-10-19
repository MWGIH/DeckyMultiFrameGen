import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  PanelSection,
  PanelSectionRow,
  staticClasses,
} from "@decky/ui";
import { definePlugin } from "@decky/api";
import { LuGalleryHorizontalEnd } from "react-icons/lu";
import {
  getBackends,
  listInstalledGames,
  logError,
  type Backend,
  type GameSummary,
} from "./api";
import { useSelectedGame } from "./hooks/useSelectedGame";
import { BackendsSection } from "./components/BackendsSection";
import { GameSection } from "./components/GameSection";
import { useHelixStatus } from "./components/HelixSRSetup";
import { useOptiStatus } from "./components/OptiScaler";
import { helixsrStatus, optiscalerStatus, type GameChoice } from "./api";
import { Content as MakoContent } from "./mako/components/Content";
import { startDailyUpdateCheck } from "./dailyUpdateCheck";

const PICKED_KEY = "multifg:picked";
const MAKO_HIDDEN_KEY = "multifg:makoHidden";
const MAKO_FULL_KEY = "multifg:makoFull";

// A boolean kept in localStorage, so the panel opens the way it was left
function usePersisted(key: string, initial: boolean) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved === null ? initial : saved === "1";
    } catch {
      return initial;
    }
  });
  const set = (next: boolean) => {
    setValue(next);
    try {
      localStorage.setItem(key, next ? "1" : "0");
    } catch {
      // just not remembered
    }
  };
  return [value, set] as const;
}
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
  const makoGame = Boolean(choice?.split("+").includes("mako"));
  // MAKO's controls: shown for a MAKO game unless hidden; light or full
  const [makoHidden, setMakoHidden] = usePersisted(MAKO_HIDDEN_KEY, false);
  const [makoFull, setMakoFull] = usePersisted(MAKO_FULL_KEY, false);
  const makoShown = makoGame && !makoHidden;
  const toggleMako = () => setMakoHidden(!makoHidden);
  // once MAKO is first installed (from Backends or its own panel), its settings open in the light view
  const makoInstalled = backends?.find((b) => b.id === "mako")?.installed;
  const makoWasInstalled = useRef<boolean | undefined>(undefined);
  useEffect(() => {
    if (makoWasInstalled.current === false && makoInstalled) {
      setMakoFull(false);
      setMakoHidden(false);
    }
    if (makoInstalled !== undefined) makoWasInstalled.current = makoInstalled;
  }, [makoInstalled]);
  const refreshOpti = () => optiscalerStatus().then(setOpti);

  const refreshBackends = () =>
    getBackends()
      .then(setBackends)
      .catch((e) => logError(`get_backends: ${e}`));
  useEffect(() => {
    refreshBackends();
    const id = setInterval(refreshBackends, BACKEND_POLL_MS);
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
      <BackendsSection
        backends={backends}
        helix={helix}
        onHelixChange={refreshHelix}
        opti={opti}
        onOptiChange={refreshOpti}
        onMakoChange={refreshBackends}
      />
      <GameSection
        selected={selected}
        games={games}
        backends={backends}
        helix={helix}
        opti={opti}
        onPick={pick}
        onChoice={setChoice}
      />
      {/* MAKO Decky's own controls (vendored, GPL-3.0) for a MAKO game, with ours to switch view or hide below */}
      {makoShown && <MakoContent variant={makoFull ? "full" : "light"} />}
      {makoGame && (
        <PanelSection title={makoShown ? undefined : "MAKO"}>
          {makoShown && (
            <PanelSectionRow>
              <ButtonItem layout="below" onClick={() => setMakoFull(!makoFull)}>
                {makoFull
                  ? "Show fewer MAKO settings"
                  : "Show all MAKO settings"}
              </ButtonItem>
            </PanelSectionRow>
          )}
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={toggleMako}>
              {makoShown ? "Hide MAKO settings" : "Show MAKO settings"}
            </ButtonItem>
          </PanelSectionRow>
        </PanelSection>
      )}
    </>
  );
}

export default definePlugin(() => {
  const stopUpdateCheck = startDailyUpdateCheck();
  return {
    name: "Decky MultiFrameGen",
    titleView: <div className={staticClasses.Title}>MultiFrameGen</div>,
    alwaysRender: true,
    content: <Content />,
    icon: <LuGalleryHorizontalEnd />,
    onDismount: stopUpdateCheck,
  };
});
