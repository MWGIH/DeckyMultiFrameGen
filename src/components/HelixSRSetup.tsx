import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  PanelSectionRow,
  ProgressBarWithInfo,
  showModal,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { promptRestart } from "../restartPrompt";
import {
  helixsrInstall,
  helixsrRemove,
  helixsrStatus,
  helixsrLog,
  type HelixJob,
  type HelixStatus,
} from "../api";

const POLL_RUNNING_MS = 1500;
const POLL_IDLE_MS = 10000;

// HelixSR's setup log (its own output and this plugin's steps), shown on request: it is long
function SetupLog() {
  const [log, setLog] = useState<{ path: string; lines: string[] } | null>(
    null,
  );
  const toggle = async (on: boolean) =>
    setLog(on ? await helixsrLog(80) : null);
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="Show HelixSR setup log"
          checked={!!log}
          onChange={toggle}
        />
      </PanelSectionRow>
      {log && (
        <PanelSectionRow>
          <Field
            label="HelixSR setup log"
            description={
              <div
                style={{
                  fontFamily: "monospace",
                  fontSize: "11px",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-all",
                }}
              >
                {`${log.path}\n\n${log.lines.join("\n") || "(empty)"}`}
              </div>
            }
          />
        </PanelSectionRow>
      )}
    </>
  );
}

// Steam's own progress bar: the stage on the left, its percentage on the right, the detail wrapping below
function Stage({
  title,
  percent,
  detail,
}: {
  title: string;
  percent?: number;
  detail?: string | null;
}) {
  return (
    <PanelSectionRow>
      <ProgressBarWithInfo
        layout="below"
        sOperationText={title}
        sTimeRemaining={
          percent === undefined ? undefined : `${Math.round(percent)}%`
        }
        nProgress={percent ?? 0}
        indeterminate={percent === undefined}
        description={detail ?? undefined}
      />
    </PanelSectionRow>
  );
}

// Download (download, checksum, unpack) and HelixSR's own setup, each with its own bar
function JobProgress({ job }: { job: HelixJob }) {
  const fraction =
    job.size && job.downloaded
      ? Math.min(1, job.downloaded / job.size)
      : undefined;
  const mb = (n?: number) => `${Math.round((n ?? 0) / 1e6)} MB`;
  const download =
    job.phase === "download"
      ? {
          percent: fraction === undefined ? undefined : fraction * 100,
          detail: job.size
            ? `${mb(job.downloaded)} of ${mb(job.size)}`
            : "Starting the download",
        }
      : job.phase === "verify"
        ? { percent: 100, detail: "Checking the download" }
        : job.phase === "extract"
          ? { percent: 100, detail: "Unpacking" }
          : { percent: 100, detail: "Done" };
  const setup =
    job.phase !== "setup"
      ? { percent: 0, detail: "Waits for the download" }
      : {
          percent: job.setup_percent ?? undefined,
          detail: job.setup_step ?? "Starting HelixSR's setup",
        };
  return (
    <>
      <Stage
        title={`Download ${job.tag}`}
        percent={download.percent}
        detail={download.detail}
      />
      <Stage title="Setup" percent={setup.percent} detail={setup.detail} />
    </>
  );
}

function confirmInstall(tag: string, onOk: () => void) {
  showModal(
    <ConfirmModal
      strTitle={`Install HelixSR ${tag}`}
      strDescription={
        "This downloads HelixSR from its GitHub releases and runs its setup. The setup downloads NVIDIA's DLSS DLL " +
        "from NVIDIA's GitHub (NVIDIA's license applies), builds the upscaling network for your GPU, then deletes " +
        "NVIDIA's DLL. From HelixSR 3.0 it also downloads about 420 MB of AMD's driver package from AMD (AMD's " +
        "license applies) and builds HLX FSR 4, its FSR drop-in, from one file in it. It takes a few minutes and " +
        "needs Proton installed in Steam. Keep the Deck awake meanwhile."
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

  // a setup that just finished: HelixSR only takes effect after a restart
  const lastState = useRef(status?.job?.state);
  useEffect(() => {
    const state = status?.job?.state;
    if (lastState.current === "running" && state === "succeeded")
      promptRestart(`HelixSR ${status?.job?.tag ?? ""}`.trim());
    lastState.current = state;
  }, [status?.job?.state]);

  return [status, setStatus] as const;
}

export function HelixSRSetup({
  status,
  onChange,
}: {
  status: HelixStatus | null;
  onChange: () => void;
}) {
  if (!status) return null;
  const job = status.job;
  const running = job?.state === "running";

  const start = (tag: string) =>
    confirmInstall(tag, async () => {
      const r = await helixsrInstall(tag);
      if (!r.ok)
        toaster.toast({
          title: "HelixSR",
          body: r.error ?? "Couldn't start the install",
        });
      onChange();
    });

  if (running && job) {
    return (
      <>
        <JobProgress job={job} />
        {status.log.length > 0 && (
          <PanelSectionRow>
            <Field
              label="Setup output"
              description={
                <div
                  style={{
                    fontFamily: "monospace",
                    fontSize: "11px",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-all",
                  }}
                >
                  {status.log.slice(-4).join("\n")}
                </div>
              }
            />
          </PanelSectionRow>
        )}
      </>
    );
  }

  const remove = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove HelixSR"
        strDescription={
          "Takes HelixSR out of every game it's in (their own files go back), then deletes HelixSR and the network " +
          "its setup built. Close your games first."
        }
        strOKButtonText="Remove"
        onOK={async () => {
          toaster.toast({ title: "HelixSR", body: "Removing HelixSR…" });
          const r = await helixsrRemove();
          toaster.toast({
            title: "HelixSR",
            body: r.ok
              ? `Removed${r.removed?.length ? ` (also from ${r.removed.join(", ")})` : ""}.`
              : (r.error ?? "Removing failed"),
          });
          onChange();
        }}
      />,
    );

  const latest = status.latest;
  return (
    <>
      {status.active_ready && (
        <PanelSectionRow>
          <Field
            label={`HelixSR ${status.active} is set up`}
            description={
              status.update_available && latest
                ? `${latest.tag} is available.`
                : latest
                  ? "Up to date. Pick HelixSR for a game above to add it there."
                  : "Pick HelixSR for a game above to add it there."
            }
          />
        </PanelSectionRow>
      )}
      {status.active_ready && status.active_hlx === false && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            label="HLX FSR 4 isn't built"
            description="The FSR drop-in needs it; HelixSR Scaler works without it. AMD's download or the build failed (see the setup log). Running the setup again only builds what is missing."
            onClick={() => status.active && start(status.active)}
          >
            Build HLX FSR 4
          </ButtonItem>
        </PanelSectionRow>
      )}
      {job?.state === "failed" && (
        <PanelSectionRow>
          <Field
            label={`HelixSR ${job.tag}: setup failed`}
            description={
              <div style={{ whiteSpace: "pre-wrap" }}>
                {[job.error, ...status.log.slice(-3)]
                  .filter(Boolean)
                  .join("\n")}
              </div>
            }
          />
        </PanelSectionRow>
      )}
      {(job?.state === "failed" || status.log.length > 0) && <SetupLog />}
      {status.active && !status.active_ready && job?.state !== "failed" && (
        <PanelSectionRow>
          <Field
            label={`HelixSR ${status.active}`}
            description="Downloaded, but its setup hasn't finished."
          />
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
      {(status.active || status.local.length > 0) && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={remove}>
            Remove HelixSR
          </ButtonItem>
        </PanelSectionRow>
      )}
      {!latest && !status.active_ready && (
        <PanelSectionRow>
          <Field
            label="HelixSR"
            description="Couldn't reach GitHub to find HelixSR's releases."
          />
        </PanelSectionRow>
      )}
    </>
  );
}
