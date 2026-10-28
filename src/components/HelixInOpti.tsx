import { useEffect, useRef, useState } from "react";
import { ButtonItem, Field, PanelSectionRow } from "@decky/ui";
import { toaster } from "@decky/api";
import { HelixLog } from "./HelixLog";
import {
  helixsrInstall,
  helixsrOptiAdd,
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
  }, [appid, refresh, helix?.active, helix?.job?.state]);
  // With OptiScaler + HelixSR chosen, HelixSR goes into OptiScaler by itself, also once HelixSR's setup finishes
  // after the game was patched. Tried once per game while the panel is open; a failure shows below.
  const tried = useRef<string | null>(null);
  useEffect(() => {
    if (!st?.ok || !st.patched || st.installed || st.needs || !helix?.active_ready) return;
    if (tried.current === appid) return;
    tried.current = appid;
    setBusy(true);
    helixsrOptiAdd(appid)
      .then((r) => toast(r.ok ? "HelixSR added to OptiScaler" : `HelixSR wasn't added: ${r.error ?? ""}`))
      .finally(() => {
        setBusy(false);
        load();
      });
  }, [st, helix?.active_ready]);

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
          description="OptiScaler isn't patched into the game yet (see above). HelixSR is added to it as soon as it is."
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

  // HelixSR 2.0 doesn't run in this OptiScaler: the newest 1.x release goes in, downloaded next to 2.0 if needed
  if (st.needs) {
    return (
      <>
        <PanelSectionRow>
          <Field
            label={`OptiScaler needs HelixSR ${st.needs}`}
            description={`HelixSR 2.0 only runs inside its own OptiScaler build (HelixSR Scaler): this OptiScaler falls back to FSR 2.1.2 with it. HelixSR ${st.needs} is downloaded and set up next to 2.0, which stays for HelixSR's own installs.`}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy || helix?.job?.state === "running"}
            onClick={() =>
              run(
                () => helixsrInstall(st.needs!),
                `Setting up HelixSR ${st.needs}: progress shows under Backends.`,
              )
            }
          >
            {helix?.job?.state === "running"
              ? "HelixSR is being set up…"
              : `Install HelixSR ${st.needs} for OptiScaler`}
          </ButtonItem>
        </PanelSectionRow>
      </>
    );
  }

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
                ? "In the game, select DLSS (or FSR / XeSS). OptiScaler then upscales with HelixSR: in OptiScaler's menu it is the FSR 3.X/4 upscaler. FSR4 is off while HelixSR is in."
                : "OptiScaler.ini was changed since HelixSR was added, so OptiScaler may not use HelixSR. Add it again to fix that."
              : "Adds HelixSR as OptiScaler's FSR 3.X upscaler. The game's own files aren't changed."
          }
        />
      </PanelSectionRow>
      {st.installed && (
        <HelixLog
          log={st.runtime_log}
          missing="HelixSR writes a log when OptiScaler loads it. If there is none after playing, check that OptiScaler's upscaler is FSR 3.X/4."
        />
      )}
      {(!st.installed || outdated || !st.ini_ok) && (
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
                ? `Use HelixSR ${st.active}`
                : "Add HelixSR again"}
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
