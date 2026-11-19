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
  helixsrSetBuild,
  type HelixExtra,
  type HelixJob,
  type HelixStatus,
} from "../api";

const POLL_RUNNING_MS = 1500;
const POLL_IDLE_MS = 10000;

// HelixSR's setup log (its own output and this plugin's steps), shown on request: it is long
export function SetupLog() {
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

function confirmInstall(tag: string, onOk: () => void, build = true) {
  showModal(
    <ConfirmModal
      strTitle={`Install HelixSR ${tag}`}
      strDescription={
        !build
          ? "This downloads HelixSR from its GitHub releases (about 280 MB). Build HelixSR is off, so its setup " +
            "doesn't run: nothing is downloaded from NVIDIA or AMD and nothing is built. Games get only the FSR " +
            "drop-in (HLX FSR 4, which comes built from HelixSR 3.3). HelixSR 3.0 to 3.2 still need their setup " +
            "for it, so for those it runs anyway."
          : "This downloads HelixSR from its GitHub releases and runs its setup. The setup downloads NVIDIA's DLSS DLL " +
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

// Build HelixSR: HelixSR's setup builds the upscaling network HLX DLSS and HelixSR Scaler run on. Off, a release that
// ships HLX FSR 4 built (3.3 on) is only downloaded, for the FSR drop-in
function BuildToggle({
  status,
  onChange,
}: {
  status: HelixStatus;
  onChange: () => void;
}) {
  const build = status.build !== false;
  const apply = async (on: boolean) => {
    const r = await helixsrSetBuild(on);
    if (!r.ok)
      toaster.toast({
        title: "HelixSR",
        body: r.error ?? "Couldn't change Build HelixSR",
      });
    else if (r.started)
      toaster.toast({
        title: "HelixSR",
        body: "Building HelixSR: progress is in Backends",
      });
    onChange();
  };
  const toggle = (on: boolean) => {
    // a downloaded release that isn't built: switching on builds it now, a long job
    const newest = status.local[0];
    if (on && newest && !(status.active === newest && status.active_ready)) {
      showModal(
        <ConfirmModal
          strTitle="Build HelixSR"
          strDescription={
            `HelixSR ${newest}'s setup runs now: it downloads NVIDIA's DLSS DLL from NVIDIA's GitHub (NVIDIA's ` +
            "license applies), builds the upscaling network for your GPU, then deletes NVIDIA's DLL. It takes a " +
            "few minutes and needs Proton installed in Steam: keep the Deck awake."
          }
          strOKButtonText="Build"
          onOK={() => apply(true)}
        />,
      );
      return;
    }
    void apply(on);
  };
  const state = build
    ? status.active_ready
      ? " Built."
      : ""
    : status.active_ready
      ? " The network already built stays: updates aren't built."
      : status.active_fsr
        ? " Not built: games get the FSR drop-in only."
        : "";
  return (
    <PanelSectionRow>
      <ToggleField
        label="Build HelixSR"
        description={
          "Needed for HLX DLSS and HelixSR Scaler. Off: HelixSR is only downloaded, with no NVIDIA download and no " +
          "long build, and games get only the FSR drop-in (HLX FSR 4, built in from HelixSR 3.3)." +
          state
        }
        checked={build}
        onChange={toggle}
      />
    </PanelSectionRow>
  );
}

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
  const build = status.build !== false;
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
        const state = !build
          ? " Part of HelixSR's build: turn on Build HelixSR first."
          : !status.active_ready
          ? e.on
            ? " Built when HelixSR is installed."
            : ""
          : !e.available
            ? ` Needs HelixSR 3.3 or newer (${status.active} is in use).`
            : e.on && e.built
              ? " Built."
              : e.on
                ? " Not built: the build failed (its setup log is under Debug at the bottom). Switch it off and on to try again."
                : "";
        return (
          <PanelSectionRow key={name}>
            <ToggleField
              label={info.label}
              description={info.about + state}
              checked={e.on}
              disabled={(!build && !e.on) || (status.active_ready && !e.available && !e.on)}
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
    if (lastState.current === "running" && state === "succeeded" && !status?.job?.no_build)
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

  const build = status.build !== false;
  // games can get HelixSR from the release in use: built, or (Build HelixSR off) the FSR drop-in only
  const usable = status.active_ready || (!build && !!status.active_fsr);
  const start = (tag: string) =>
    confirmInstall(
      tag,
      async () => {
        const r = await helixsrInstall(tag);
        if (!r.ok)
          toaster.toast({
            title: "HelixSR",
            body: r.error ?? "Couldn't start the install",
          });
        onChange();
      },
      build,
    );

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
      <BuildToggle status={status} onChange={onChange} />
      <ExtraToggles status={status} onChange={onChange} />
      {status.active_ready && status.active_hlx === false && (
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            label="HLX FSR 4 isn't built"
            description="The FSR drop-in needs it; HelixSR Scaler works without it. AMD's download or the build failed (its setup log is under Debug at the bottom). Running the setup again only builds what is missing."
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
      {status.active && !usable && job?.state !== "failed" && (
        <PanelSectionRow>
          <Field
            label={`HelixSR ${status.active}`}
            description="Downloaded, but its setup hasn't finished."
          />
        </PanelSectionRow>
      )}
      {latest && (status.update_available || !usable) && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => start(latest.tag)}>
            {usable
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
      {!latest && !usable && (
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
