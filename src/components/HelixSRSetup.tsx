import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  PanelSectionRow,
  showModal,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import { promptRestart } from "../restartPrompt";
import { ProgressRow } from "./ProgressRow";
import {
  helixsrInstall,
  helixsrRemove,
  helixsrStatus,
  helixsrLog,
  helixsrSetPrereleases,
  helixsrSetExtra,
  type HelixExtra,
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

const EXTRA_TITLE: Record<HelixExtra, string> = {
  vulkan: "Vulkan kernels",
  preset_k: "Preset K",
};

// Download (download, checksum, unpack), HelixSR's own setup and each optional extra it builds, each with its own bar
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
      <ProgressRow
        title={`Download ${job.tag}`}
        percent={download.percent}
        detail={download.detail}
      />
      <ProgressRow title="Setup" percent={setup.percent} detail={setup.detail} />
      {(job.extras ?? []).map((name) => {
        const p = job.phase === "setup" ? job.extras_progress?.[name] : undefined;
        return (
          <ProgressRow
            key={name}
            title={
              p?.state === "failed"
                ? `${EXTRA_TITLE[name]}: not built`
                : EXTRA_TITLE[name]
            }
            percent={
              !p || p.state === "waiting"
                ? 0
                : (p.percent ?? undefined)
            }
            detail={p?.step ?? "Waits for the setup"}
          />
        );
      })}
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
        "NVIDIA's DLL. HelixSR 3.0 to 3.2 also download about 420 MB of AMD's driver package from AMD (AMD's " +
        "license applies) to build HLX FSR 4, their FSR drop-in; from 3.3 it comes built. It takes a few minutes " +
        "(more with the Preset K or Vulkan kernels options on) and needs Proton installed in Steam. Keep the Deck " +
        "awake meanwhile."
      }
      strOKButtonText="Install"
      onOK={onOk}
    />,
  );
}

const EXTRA_INFO: Record<
  HelixExtra,
  { label: string; about: string; confirm: string; offConfirm?: string }
> = {
  preset_k: {
    label: "Build Preset K",
    about:
      "NVIDIA's DLSS 4 Preset K network for HLX DLSS: sharper, a little slower. Pick it in HelixSR Scaler's DLSS " +
      "Upscaler list. Tested on AMD RDNA GPUs only; a game can freeze at start with Steam's overlay on.",
    confirm:
      "HelixSR's setup runs again now and builds Preset K. It can take many minutes: keep the Deck awake. " +
      "Games get it when HelixSR is installed into them again.",
  },
  vulkan: {
    label: "Build Vulkan kernels",
    about:
      "Lets HLX DLSS run natively in Vulkan games instead of through HelixSR Scaler's DirectX 12 bridge. " +
      "Switching it on or off builds HelixSR's network again.",
    confirm:
      "HelixSR's setup builds its network again now, with the Vulkan kernels. This takes a long time (it can sit " +
      "at 70% for a while): keep the Deck awake. Games get them when HelixSR is installed into them again.",
    offConfirm:
      "HelixSR's setup builds its network again now, without the Vulkan kernels. This takes as long as the first " +
      "build: keep the Deck awake.",
  },
};

// Preset K and the Vulkan kernels: optional extras of HelixSR's setup (HelixSR 3.3 on), off by default
function ExtraToggles({
  status,
  onChange,
}: {
  status: HelixStatus;
  onChange: () => void;
}) {
  const extras = status.extras;
  if (!extras) return null;
  const apply = async (name: HelixExtra, on: boolean) => {
    const r = await helixsrSetExtra(name, on);
    if (!r.ok)
      toaster.toast({
        title: "HelixSR",
        body: r.error ?? "Couldn't change the option",
      });
    else if (r.started)
      toaster.toast({
        title: "HelixSR",
        body: `Building ${EXTRA_TITLE[name]}: progress is in Backends`,
      });
    onChange();
  };
  const toggle = (name: HelixExtra, on: boolean) => {
    const e = extras[name];
    const info = EXTRA_INFO[name];
    // HelixSR is set up and the change needs a build now: ask first, it's a long one
    const builds =
      status.active_ready &&
      e.available &&
      (on ? !e.built : name === "vulkan" && e.built);
    if (!builds) {
      void apply(name, on);
      return;
    }
    showModal(
      <ConfirmModal
        strTitle={`${on ? "Build" : "Remove"} ${EXTRA_TITLE[name]}`}
        strDescription={on ? info.confirm : (info.offConfirm ?? info.confirm)}
        strOKButtonText={on ? "Build" : "Rebuild"}
        onOK={() => apply(name, on)}
      />,
    );
  };
  return (
    <>
      {(Object.keys(EXTRA_INFO) as HelixExtra[]).map((name) => {
        const e = extras[name];
        const info = EXTRA_INFO[name];
        const state = !status.active_ready
          ? e.on
            ? " Built when HelixSR is installed."
            : ""
          : !e.available
            ? ` Needs HelixSR 3.3 or newer (${status.active} is in use).`
            : e.on && e.built
              ? " Built."
              : e.on
                ? " Not built: the build failed (see the setup log). Switch it off and on to try again."
                : "";
        return (
          <PanelSectionRow key={name}>
            <ToggleField
              label={info.label}
              description={info.about + state}
              checked={e.on}
              disabled={status.active_ready && !e.available && !e.on}
              onChange={(on) => toggle(name, on)}
            />
          </PanelSectionRow>
        );
      })}
    </>
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
      {/* the installed version is in the HelixSR line above: only what is new goes here */}
      <PanelSectionRow>
        <ToggleField
          label="Offer HelixSR pre-releases"
          description={
            status.newer_prerelease && !status.prereleases
              ? `${status.newer_prerelease} is out as a pre-release. Turn this on to install it.`
              : "Off: only HelixSR's stable releases are offered."
          }
          checked={!!status.prereleases}
          onChange={async (on) => {
            await helixsrSetPrereleases(on);
            onChange();
          }}
        />
      </PanelSectionRow>
      <ExtraToggles status={status} onChange={onChange} />
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
