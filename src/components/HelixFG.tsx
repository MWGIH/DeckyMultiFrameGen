import { useEffect, useState } from "react";
import { ButtonItem, PanelSectionRow, ToggleField } from "@decky/ui";
import { toaster } from "@decky/api";
import { helixsrFg, helixsrFixStreamline, type HelixFgStatus } from "../api";

function toast(body: string) {
  toaster.toast({ title: "HelixSR frame generation", body });
}

// HelixSR's own frame generation in a game with HelixSR Scaler: its switch, the Streamline plugins OptiScaler's own
// Streamline lacks (multifg.helix_fg). Its log is in the Debug section.
export function HelixFG({ appid }: { appid: string }) {
  const [fg, setFg] = useState<HelixFgStatus | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => helixsrFg(appid).then(setFg);
  useEffect(() => {
    setFg(null);
    load();
  }, [appid]);

  if (!fg?.ok) return null;

  const fixStreamline = async () => {
    setBusy(true);
    try {
      const r = await helixsrFixStreamline(appid);
      toast(
        r.ok
          ? `Added ${r.added?.join(", ") || "nothing"}. Restart the game.`
          : (r.error ?? "Couldn't get the files"),
      );
    } finally {
      setBusy(false);
      load();
    }
  };

  const toggle = async (on: boolean) => {
    setBusy(true);
    try {
      const r = await helixsrFg(appid, on);
      if (!r.ok) toast(r.error ?? "Couldn't switch it");
      else if (on) toast("On. In the game, turn on DLSS, DLSS Frame Generation and Reflex.");
    } finally {
      setBusy(false);
      load();
    }
  };

  const missing = fg.streamline?.missing ?? [];
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="HelixSR frame generation"
          description={
            fg.blocked
              ? fg.blocked
              : !fg.available
              ? "Not in this game: HelixSR 3.4 or newer builds it with its setup; install HelixSR in the game again afterwards."
              : "Runs when the game's DLSS Frame Generation is on. It spoofs an NVIDIA GPU and hardware GPU scheduling so the game offers it, and turns off OptiScaler's .asi plugins (OptiPatcher), which undo the spoofing. Close the game first."
          }
          checked={!!fg.enabled}
          // when blocked it can still be switched off (turned on before the game got MAKO or an anti-cheat note)
          disabled={busy || !fg.available || (!!fg.blocked && !fg.enabled)}
          onChange={toggle}
        />
      </PanelSectionRow>
      {missing.length > 0 && !fg.blocked && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            description={`OptiScaler's Streamline ${fg.streamline?.version ?? ""} lacks ${missing.join(", ")}, which the game ships. OptiScaler warns about it in the game; DLSS can fail without them.`}
            onClick={fixStreamline}
          >
            Get the missing Streamline files from NVIDIA
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
