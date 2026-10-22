import { useEffect, useState } from "react";
import { PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { optiscalerLogging } from "../api";

// OptiScaler's own log file for the game, off by default: on, it shows how far a game gets when it crashes
export function OptiLog({ appid }: { appid: string }) {
  const [state, setState] = useState<{ on: boolean; path?: string } | null>(
    null,
  );
  const load = () =>
    optiscalerLogging(appid).then((r) =>
      setState(r.ok ? { on: !!r.logging, path: r.path } : null),
    );
  useEffect(() => {
    load();
  }, [appid]);
  if (!state) return null;
  return (
    <PanelSectionRow>
      <ToggleField
        label="Write OptiScaler's log"
        description={`Off by default. On, OptiScaler writes ${state.path ?? "OptiScaler.log"}, which shows how far the game gets when it crashes. It slows the game a little: turn it off again afterwards.`}
        checked={state.on}
        onChange={async (on) => {
          const r = await optiscalerLogging(appid, on);
          if (!r.ok)
            toaster.toast({
              title: "OptiScaler",
              body: r.error ?? "Couldn't change OptiScaler's log",
            });
          load();
        }}
      />
    </PanelSectionRow>
  );
}
