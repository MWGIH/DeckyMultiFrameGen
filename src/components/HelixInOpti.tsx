import { useEffect, useState } from "react";
import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { HelixLog } from "./HelixLog";
import {
  helixsrOptiAdd,
  helixsrOptiRemove,
  helixsrOptiStatus,
  type HelixInOpti,
  type HelixStatus,
} from "../api";

const toast = (body: string) => toaster.toast({ title: "HelixSR", body });

// HelixSR as OptiScaler's FSR 3.1 upscaler. refresh changes when OptiScaler is patched or unpatched.
export function HelixInOptiGame({
  appid,
  helix,
  refresh,
}: {
  appid: string;
  helix: HelixStatus | null;
  refresh: number;
}) {
  const [st, setSt] = useState<HelixInOpti | null>(null);
  const [busy, setBusy] = useState(false);
  const load = () => helixsrOptiStatus(appid).then(setSt);
  useEffect(() => {
    load();
  }, [appid, refresh, helix?.active]);

  if (!helix?.active_ready) {
    return (
      <PanelSectionRow>
        <Field
          label="HelixSR in OptiScaler"
          description="Set up HelixSR below first."
        />
      </PanelSectionRow>
    );
  }
  if (!st) return null;
  if (!st.ok) {
    return (
      <PanelSectionRow>
        <Field label="HelixSR in OptiScaler" description={st.error} />
      </PanelSectionRow>
    );
  }
  if (!st.patched) {
    return (
      <PanelSectionRow>
        <Field
          label="HelixSR in OptiScaler"
          description="Patch the game with OptiScaler above. HelixSR is added to it at the same time."
        />
      </PanelSectionRow>
    );
  }

  const run = async (
    work: () => Promise<{ ok: boolean; error?: string }>,
    done: string,
  ) => {
    setBusy(true);
    try {
      const r = await work();
      toast(r.ok ? done : (r.error ?? "That didn't work"));
    } finally {
      setBusy(false);
      load();
    }
  };
  const outdated =
    st.installed && st.helixsr && st.active && st.helixsr !== st.active;

  return (
    <>
      <PanelSectionRow>
        <Field
          label={
            st.installed
              ? `HelixSR in OptiScaler (${st.helixsr ?? "installed"})`
              : "HelixSR not in OptiScaler"
          }
          description={
            st.installed
              ? st.ini_ok
                ? "In the game, select DLSS (or FSR / XeSS). OptiScaler then upscales with HelixSR: in OptiScaler's menu it is the FSR 3.X upscaler. FSR4 is off while HelixSR is in."
                : "OptiScaler.ini was changed since HelixSR was added, so OptiScaler may not use HelixSR. Add it again to fix that."
              : "Adds HelixSR as OptiScaler's FSR 3.X upscaler. The game's own files aren't changed."
          }
        />
      </PanelSectionRow>
      {st.installed && (
        <HelixLog
          log={st.runtime_log}
          missing="HelixSR writes a log when OptiScaler loads it. If there is none after playing, check that OptiScaler's upscaler is FSR 3.X."
        />
      )}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy}
          onClick={() =>
            run(() => helixsrOptiAdd(appid), "HelixSR added to OptiScaler")
          }
        >
          {!st.installed
            ? "Add HelixSR to OptiScaler"
            : outdated
              ? `Update HelixSR to ${st.active}`
              : !st.ini_ok
                ? "Add HelixSR again"
                : "Reinstall HelixSR"}
        </ButtonItem>
      </PanelSectionRow>
      {st.installed && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() =>
              run(
                () => helixsrOptiRemove(appid),
                "HelixSR removed from OptiScaler",
              )
            }
          >
            Remove HelixSR from OptiScaler
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
