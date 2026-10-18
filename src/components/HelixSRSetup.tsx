import { useEffect, useState } from "react";
import { ButtonItem, ConfirmModal, Field, PanelSectionRow, ProgressBarWithInfo, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import { helixsrInstall, helixsrStatus, type HelixStatus } from "../api";

const POLL_RUNNING_MS = 1500;
const POLL_IDLE_MS = 10000;

const PHASES = {
  download: "Downloading HelixSR",
  verify: "Checking the download",
  extract: "Unpacking",
  setup: "Running HelixSR's setup (builds the upscaling network, a few minutes)",
};

function confirmInstall(tag: string, onOk: () => void) {
  showModal(
    <ConfirmModal
      strTitle={`Install HelixSR ${tag}`}
      strDescription={
        "This downloads HelixSR from its GitHub releases and runs its setup. The setup downloads NVIDIA's DLSS DLL " +
        "from NVIDIA's GitHub (NVIDIA's license applies), builds the upscaling network for your GPU, then deletes " +
        "NVIDIA's DLL. It takes a few minutes and needs Proton installed in Steam. Keep the Deck awake meanwhile."
      }
      strOKButtonText="Install"
      onOK={onOk}
    />,
  );
}

export function useHelixStatus() {
  const [status, setStatus] = useState<HelixStatus | null>(null);
  const running = status?.job?.state === "running";

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      helixsrStatus()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    load();
    const id = setInterval(load, running ? POLL_RUNNING_MS : POLL_IDLE_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [running]);

  return [status, setStatus] as const;
}

export function HelixSRSetup({ status, onChange }: { status: HelixStatus | null; onChange: () => void }) {
  if (!status) return null;
  const job = status.job;
  const running = job?.state === "running";

  const start = (tag: string) =>
    confirmInstall(tag, async () => {
      const r = await helixsrInstall(tag);
      if (!r.ok) toaster.toast({ title: "HelixSR", body: r.error ?? "Couldn't start the install" });
      onChange();
    });

  if (running && job) {
    const progress =
      job.phase === "download" && job.size && job.downloaded ? Math.min(1, job.downloaded / job.size) : undefined;
    return (
      <>
        <PanelSectionRow>
          <ProgressBarWithInfo
            label={`HelixSR ${job.tag}`}
            description={PHASES[job.phase]}
            nProgress={progress === undefined ? undefined : progress * 100}
            indeterminate={progress === undefined}
            sOperationText={progress === undefined ? undefined : `${Math.round(progress * 100)}%`}
          />
        </PanelSectionRow>
        {status.log.length > 0 && (
          <PanelSectionRow>
            <Field
              label="Setup output"
              description={
                <div style={{ fontFamily: "monospace", fontSize: "11px", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {status.log.slice(-4).join("\n")}
                </div>
              }
            />
          </PanelSectionRow>
        )}
      </>
    );
  }

  const latest = status.latest;
  return (
    <>
      {job?.state === "failed" && (
        <PanelSectionRow>
          <Field
            label={`HelixSR ${job.tag}: setup failed`}
            description={
              <div style={{ whiteSpace: "pre-wrap" }}>
                {[job.error, ...status.log.slice(-3)].filter(Boolean).join("\n")}
              </div>
            }
          />
        </PanelSectionRow>
      )}
      {status.active && !status.active_ready && job?.state !== "failed" && (
        <PanelSectionRow>
          <Field label={`HelixSR ${status.active}`} description="Downloaded, but its setup hasn't finished." />
        </PanelSectionRow>
      )}
      {latest && (status.update_available || !status.active_ready) && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => start(latest.tag)}>
            {status.active_ready
              ? `Update HelixSR to ${latest.tag}`
              : status.local.includes(latest.tag)
                ? `Run HelixSR ${latest.tag} setup`
                : `Install HelixSR ${latest.tag}`}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {!latest && !status.active_ready && (
        <PanelSectionRow>
          <Field label="HelixSR" description="Couldn't reach GitHub to find HelixSR's releases." />
        </PanelSectionRow>
      )}
    </>
  );
}
