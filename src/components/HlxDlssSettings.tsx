import { useEffect, useState } from "react";
import { Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { BelowDropdown } from "./BelowDropdown";
import {
  helixsrDlss,
  type HlxDeepReuse,
  type HlxDlss,
  type HlxNetworkResolution,
} from "../api";

const DEEP_REUSE = [
  { data: "default", label: "Default (exact)" },
  { data: "1:2", label: "1:2" },
  { data: "1:4", label: "1:4" },
];

const NETWORK_RESOLUTION = [
  { data: "full", label: "Full" },
  { data: "fast", label: "Fast" },
];

// HLX DLSS's speed settings (HelixSR 3.4+): the deeper network layers' reuse and Ultra Performance's output size,
// both in helixsr.ini (multifg.helix_dlss). Shown where HLX DLSS is HelixSR's upscaler.
export function HlxDlssSettings({
  appid,
  enabled = true,
}: {
  appid: string;
  enabled?: boolean;
}) {
  const [st, setSt] = useState<HlxDlss | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setSt(null);
    if (enabled) helixsrDlss(appid).then(setSt);
  }, [appid, enabled]);

  if (!enabled || !st?.ok) return null;

  const save = async (deep?: HlxDeepReuse, network?: HlxNetworkResolution) => {
    setBusy(true);
    try {
      // "" leaves the other setting as it is
      const r = await helixsrDlss(appid, deep ?? "", network ?? "");
      if (r.ok) {
        setSt(r);
        toaster.toast({ title: "HLX DLSS", body: "Restart the game to apply." });
      } else {
        toaster.toast({
          title: "HLX DLSS",
          body: r.error ?? "Couldn't change it",
        });
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label="HLX DLSS speed"
          description="HelixSR reads these when the game starts: restart the game after a change."
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <BelowDropdown
          label="Network reuse (Balanced/Performance)"
          description="Runs HLX DLSS's deeper layers every second or fourth frame: faster, a little softer in fast motion. No effect at Ultra Performance."
          rgOptions={DEEP_REUSE}
          selectedOption={st.deep_reuse ?? "default"}
          disabled={busy}
          onChange={(o) => save(o.data as HlxDeepReuse)}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <BelowDropdown
          label="Ultra Performance network"
          description="Ultra Performance only. Fast has the network output twice the render size and scales it to the screen: about 30% less GPU time there, visibly softer."
          rgOptions={NETWORK_RESOLUTION}
          selectedOption={st.network_resolution ?? "full"}
          disabled={busy}
          onChange={(o) => save(undefined, o.data as HlxNetworkResolution)}
        />
      </PanelSectionRow>
    </>
  );
}
