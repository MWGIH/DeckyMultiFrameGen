import { useEffect, useState } from "react";
import { Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  anrGameStatus,
  helixsrGameStatus,
  helixsrOptiStatus,
  helixsrScalerLogging,
  type AnrGame,
  type GameChoice,
  type HelixGame,
  type HelixInOpti,
  type HelixStatus,
} from "../api";
import { OptiLog } from "./OptiLog";
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
  const load = () => helixsrGameStatus(appid).then(setGame);
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
  const gameDebug = !!appid && (opti || helixParts || choice === "anrfg");
  return (
    <PanelSection title="Debug">
      <PanelSectionRow>
        <ToggleField
          label="Show debug options"
          description={shown ? undefined : "Logs and log switches for the game's methods and HelixSR's setup."}
          checked={shown}
          onChange={setShown}
        />
      </PanelSectionRow>
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
