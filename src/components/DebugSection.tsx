import { useEffect, useState } from "react";
import { Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  anrGameStatus,
  getGame,
  type GameDetail,
  helixsrFg,
  helixsrGameStatus,
  helixsrOptiStatus,
  helixsrScalerLogging,
  type AnrGame,
  type GameChoice,
  type HelixFgStatus,
  type HelixGame,
  type HelixInOpti,
  type HelixStatus,
} from "../api";
import { OptiLog } from "./OptiLog";
import { GameFiles } from "./GameFiles";
import { useShowAll } from "../showAll";
import { HelixLog } from "./HelixLog";
import { SetupLog } from "./HelixSRSetup";

const SHOWN_KEY = "multifg:debugShown";

function readShown(): boolean {
  try {
    return localStorage.getItem(SHOWN_KEY) === "1";
  } catch {
    return false;
  }
}

// HelixSR on its own in the game: its log, and OptiScaler's log for HelixSR Scaler
function HelixGameDebug({ appid }: { appid: string }) {
  const [game, setGame] = useState<HelixGame | null>(null);
  const [fg, setFg] = useState<HelixFgStatus | null>(null);
  const load = () =>
    helixsrGameStatus(appid).then((g) => {
      setGame(g);
      if (g?.installed && g.current === "scaler") helixsrFg(appid).then(setFg);
      else setFg(null);
    });
  useEffect(() => {
    load();
  }, [appid]);
  if (!game?.installed) return null;
  return (
    <>
      <HelixLog
        log={game.runtime_log}
        missing="HelixSR writes a log when the game loads it. If there is none after playing with the right upscaler selected, the game didn't load HelixSR."
      />
      {game.current === "scaler" && (
        <PanelSectionRow>
          <ToggleField
            label="Write OptiScaler's log"
            description="Off by default. On, HelixSR Scaler writes OptiScaler.log next to the game's .exe, which shows how far the game gets when it crashes before HelixSR loads. It slows the game a little: turn it off again afterwards."
            checked={!!game.opti_logging}
            onChange={async (on) => {
              const r = await helixsrScalerLogging(appid, on);
              if (!r.ok)
                toaster.toast({ title: "HelixSR", body: r.error ?? "Couldn't change OptiScaler's log" });
              load();
            }}
          />
        </PanelSectionRow>
      )}
      {game.current === "scaler" && fg?.ok && fg.enabled && (
        <HelixLog
          name="HelixSR frame generation"
          log={fg.log}
          missing="It writes a log once the game turns DLSS Frame Generation on."
        />
      )}
    </>
  );
}

// HelixSR inside OptiScaler: HelixSR's log (OptiScaler's own log comes from OptiLog)
function HelixInOptiDebug({ appid }: { appid: string }) {
  const [st, setSt] = useState<HelixInOpti | null>(null);
  useEffect(() => {
    helixsrOptiStatus(appid).then(setSt);
  }, [appid]);
  if (!st?.installed) return null;
  return (
    <HelixLog
      log={st.runtime_log}
      missing="HelixSR writes a log when OptiScaler loads it. If there is none after playing, check that OptiScaler's upscaler is FSR 3.X/4."
    />
  );
}

function AnrDebug({ appid }: { appid: string }) {
  const [game, setGame] = useState<AnrGame | null>(null);
  useEffect(() => {
    anrGameStatus(appid).then(setGame);
  }, [appid]);
  if (!game?.log) return null;
  return (
    <PanelSectionRow>
      <Field label="Newest ANR FG log" description={game.log} />
    </PanelSectionRow>
  );
}

// The game's .exe and upscaler files (read again each time Debug opens or the choice changes)
function GameFilesDebug({ appid, choice }: { appid: string; choice: GameChoice | null }) {
  const [detail, setDetail] = useState<GameDetail | null>(null);
  useEffect(() => {
    getGame(appid).then(setDetail);
  }, [appid, choice]);
  if (!detail?.ok || !detail.installed) return null;
  return <GameFiles files={detail.files} running={detail.running_exes} />;
}

// Logs and log switches of every method, hidden until asked for, at the bottom of the panel
export function DebugSection({
  appid,
  choice,
  helix,
}: {
  appid: string | null;
  choice: GameChoice | null;
  helix: HelixStatus | null;
}) {
  const [shown, setShownState] = useState(readShown);
  const [showAll, setShowAll] = useShowAll();
  const setShown = (on: boolean) => {
    setShownState(on);
    try {
      localStorage.setItem(SHOWN_KEY, on ? "1" : "0");
    } catch {
      // just not remembered
    }
  };
  const parts = choice ? choice.split("+") : [];
  const opti = parts.includes("optiscaler");
  const helixParts = parts.includes("helixsr");
  const setupLog = !!helix && (helix.job?.state === "failed" || helix.log.length > 0);
  const gameDebug = !!appid;
  return (
    <PanelSection title="Debug">
      <PanelSectionRow>
        <ToggleField
          label="Show debug options"
          description={shown ? undefined : "Show all Use options, the game's upscaler files, and logs."}
          checked={shown}
          onChange={setShown}
        />
      </PanelSectionRow>
      {shown && appid && (
        <PanelSectionRow>
          <ToggleField
            label="Show all Use options"
            description={
              showAll
                ? "Every installed method is offered, whatever the game ships."
                : "Off: only the methods that can work with the game's upscaler files. Turn on if detection got it wrong or to experiment."
            }
            checked={showAll}
            onChange={setShowAll}
          />
        </PanelSectionRow>
      )}
      {shown && appid && <GameFilesDebug key={appid} appid={appid} choice={choice} />}
      {shown && appid && opti && <OptiLog key={appid} appid={appid} />}
      {shown && appid && helixParts && !opti && <HelixGameDebug key={appid} appid={appid} />}
      {shown && appid && helixParts && opti && <HelixInOptiDebug key={appid} appid={appid} />}
      {shown && appid && choice === "anrfg" && <AnrDebug key={appid} appid={appid} />}
      {shown && setupLog && <SetupLog />}
      {shown && !gameDebug && !setupLog && (
        <PanelSectionRow>
          <Field
            label="Nothing to show"
            description="Logs appear here for games set to OptiScaler, HelixSR or ANR FG, and for HelixSR's setup."
          />
        </PanelSectionRow>
      )}
    </PanelSection>
  );
}
