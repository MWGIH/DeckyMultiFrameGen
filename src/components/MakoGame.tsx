import { useEffect, useState } from "react";
import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { makoGameLaunchOptions } from "../api";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

function toast(body: string) {
  toaster.toast({ title: "MAKO", body });
}

// MAKO works through its launcher in the game's launch options; its settings are in the MAKO controls below.
export function MakoGame({ appid, makoInstalled, losslessScaling }: { appid: string; makoInstalled: boolean; losslessScaling: boolean }) {
  const id = Number(appid);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const current = await readLaunchOptions(id);
    if (current === null) return setEnabled(null);
    const r = await makoGameLaunchOptions(current, false);
    setEnabled(r.launch_options !== current);
  };
  useEffect(() => {
    setEnabled(null);
    load();
  }, [appid, makoInstalled]);

  const change = async (enable: boolean) => {
    setBusy(true);
    try {
      const current = await readLaunchOptions(id);
      if (current === null) return toast("Couldn't read the game's launch options.");
      const r = await makoGameLaunchOptions(current, enable);
      if (!r.ok || r.launch_options === undefined) return toast(r.error ?? "Couldn't change the launch options");
      if (!writeLaunchOptions(id, r.launch_options)) {
        toast(`Couldn't set the launch options. Set them in Steam: ${r.launch_options || "(empty)"}`);
      } else {
        toast(enable ? "MAKO added to the launch options." : "MAKO taken out of the launch options.");
      }
    } finally {
      setBusy(false);
      load();
    }
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label={
            !makoInstalled
              ? "MAKO isn't installed"
              : enabled
                ? "MAKO is on for this game"
                : enabled === false
                  ? "MAKO isn't in this game's launch options"
                  : "Checking the launch options…"
          }
          description={
            !makoInstalled
              ? "Install it in the MAKO controls below, then add it to this game."
              : losslessScaling
                ? "Change frame generation, scaling and shaders in the MAKO controls below."
                : "Frame generation needs Lossless Scaling installed in Steam. Scaling and shaders work without it."
          }
        />
      </PanelSectionRow>
      {makoInstalled && enabled !== null && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={() => change(!enabled)}>
            {enabled ? "Take MAKO out of the launch options" : "Add MAKO to the launch options"}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
