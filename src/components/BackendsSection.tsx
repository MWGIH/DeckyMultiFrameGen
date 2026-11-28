import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  PanelSection,
  PanelSectionRow,
  showModal,
  ToggleField,
} from "@decky/ui";
import {
  checkUpdates,
  makoGameLaunchOptions,
  makoGames,
  pluginVersion,
  type Backend,
  type Fsr4Status,
  type AnrStatus,
  type HelixStatus,
  type OptiStatus,
} from "../api";
import { Fsr4Setup } from "./FSR4Injector";
import { AnrSetup } from "./ANRFG";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";
import { HelixSRSetup } from "./HelixSRSetup";
import { OptiScalerSetup } from "./OptiScaler";
import { UpdatesCheck, updateAll, type UpdateRefresh } from "./UpdatesCheck";
import { installMako, uninstallMako } from "../mako/api/makoApi";
import { toaster } from "@decky/api";
import { promptRestart } from "../restartPrompt";
import { rememberUpdates, useAvailableUpdates } from "../dailyUpdateCheck";
import { ProgressRow } from "./ProgressRow";
import { backendProgress, jobRunning, type BatchName, type UpdateJobs } from "../updateProgress";
import { FirstRunSetup, InstallMoreButton, showGetStarted, useSetupDone } from "./FirstRunSetup";
import { finishInstall, setInstallState, useInstallState, type Batch } from "../installs";

function statusLine(b: Backend): string {
  if (b.error) return `Couldn't check: ${b.error}`;
  if (!b.installed) return "Not installed";
  return b.version ? `Installed (${b.version})` : "Installed";
}

type Props = {
  backends: Backend[] | null;
  helix: HelixStatus | null;
  onHelixChange: () => void;
  opti: OptiStatus | null;
  onOptiChange: () => void;
  onMakoChange: () => void;
  fsr4: Fsr4Status | null;
  onFsr4Change: () => void;
  anr: AnrStatus | null;
  onAnrChange: () => void;
};

const COLLAPSED_KEY = "multifg:backendsCollapsed";

// Backends start hidden: they're needed rarely, the game comes first
function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) !== "0";
  } catch {
    return true;
  }
}

export function useBackendsCollapsed() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // just not remembered
    }
  };
  return [collapsed, toggle] as const;
}

function usePluginVersion() {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    pluginVersion()
      .then(setVersion)
      .catch(() => undefined);
  }, []);
  return version;
}

// At the top of the panel: the update notice with Update All, and the Show backends switch; the backends open at
// the bottom
export function BackendsHeader({
  backends,
  helix,
  collapsed,
  onToggle,
  jobs,
  onUpdated,
}: {
  backends: Backend[] | null;
  helix: HelixStatus | null;
  collapsed: boolean;
  onToggle: () => void;
  jobs: UpdateJobs;
  onUpdated: UpdateRefresh;
}) {
  const version = usePluginVersion();
  const [setupDone, markSetupDone] = useSetupDone();
  const gettingStarted = showGetStarted(backends, setupDone);
  // the installed MultiFrameGen isn't an update (it was found before this one was installed)
  const updates = useAvailableUpdates().filter(
    (u) => !(version && u === `MultiFrameGen ${version}`),
  );
  // the update or install run going on: what it does, and which backends have been seen running (shared with the
  // first-time setup and Use's install-on-pick, so there is one bar)
  const { batch, starting } = useInstallState();
  const setBatch = (b: Batch | null) => setInstallState({ batch: b });
  const setStarting = (s: string | null) => setInstallState({ starting: s });
  const running = [jobs.opti, jobs.helix, jobs.fsr4, jobs.anr].some((j) => j?.state === "running");
  // a backend counts as finished once its job ran and stopped (or, if it was too quick to be seen, after a while)
  const finished = (n: BatchName) =>
    n === "MAKO" ||
    (!jobRunning(n, jobs) && (batch!.seen.includes(n) || Date.now() - batch!.at > 20000));
  useEffect(() => {
    if (!batch) return;
    const nowRunning = batch.names.filter((n) => jobRunning(n, jobs) && !batch.seen.includes(n));
    if (nowRunning.length) setBatch({ ...batch, seen: [...batch.seen, ...nowRunning] });
    else if (batch.names.every(finished)) {
      const failed = batch.names.filter((n) => backendProgress(n, jobs).stage === "failed");
      setBatch(null);
      Object.values(onUpdated).forEach((f) => f());
      if (batch.kind === "install") {
        finishInstall({
          names: batch.names,
          failed,
          startFailed: batch.startFailed,
          helixBuild: batch.helixBuild,
          after: batch.after
            ? (f) => batch.after!([...(batch.startFailedNames ?? []), ...f])
            : undefined,
        });
      } else
        toaster.toast({
          title: "Updates",
          body: failed.length
            ? `Updated, except ${failed.join(", ")}: show backends for what went wrong.`
            : `${batch.names.join(", ")} updated.`,
        });
      checkUpdates()
        .then(rememberUpdates)
        .catch(() => undefined);
    }
  }, [jobs, batch]);
  // a run started elsewhere (Backends' own buttons) still clears the notice when it ends
  const wasRunning = useRef(running);
  useEffect(() => {
    if (wasRunning.current && !running && !batch)
      checkUpdates()
        .then(rememberUpdates)
        .catch(() => undefined);
    wasRunning.current = running;
  }, [running]);
  const updateAllNow = async () => {
    setStarting("Checking for updates");
    try {
      const u = await checkUpdates();
      rememberUpdates(u);
      const r = await updateAll(u, onUpdated, (name) => setStarting(`Starting ${name}`));
      const names = r.started as BatchName[];
      if (names.some((n) => n !== "MAKO")) setBatch({ kind: "update", names, seen: [], at: Date.now() });
      else if (names.length) toaster.toast({ title: "Updates", body: `${names.join(", ")} updated.` });
      if (r.message) toaster.toast({ title: "Updates", body: r.message });
    } catch (e) {
      toaster.toast({ title: "Updates", body: `Couldn't update: ${e}` });
    } finally {
      setStarting(null);
    }
  };
  // one bar over everything being updated: each backend's share is the same, its stages fill it
  const progress = batch
    ? (() => {
        const each = batch.names.map((n) => ({ n, ...backendProgress(n, jobs), done: finished(n) }));
        const fraction = each.reduce((t, e) => t + (e.done ? 1 : jobRunning(e.n, jobs) ? e.fraction : 0), 0) / each.length;
        const current = each.find((e) => !e.done);
        const doneCount = each.filter((e) => e.done).length;
        return {
          percent: fraction * 100,
          title: current
            ? `${batch.kind === "install" ? "Installing" : "Updating"} ${current.n} (${Math.min(doneCount + 1, each.length)} of ${each.length})`
            : batch.kind === "install"
              ? "Finishing the installs"
              : "Finishing the updates",
          detail: current ? (jobRunning(current.n, jobs) ? current.stage : "starting") : null,
        };
      })()
    : null;
  const busy = !!starting || !!batch;
  return (
    <>
    <FirstRunSetup
      backends={backends}
      helix={helix}
      refresh={onUpdated}
      done={setupDone}
      markDone={markSetupDone}
    />
    <PanelSection title="Backends">
      {starting && <ProgressRow title={starting} detail="Don't close Steam until this is done." />}
      {progress && <ProgressRow title={progress.title} percent={progress.percent} detail={progress.detail} />}
      {updates.length > 0 && !batch && (
        <>
          <PanelSectionRow>
            <Field
              label={updates.length > 1 ? "Updates available" : "Update available"}
              description={`${updates.join(", ")}.`}
              bottomSeparator="none"
            />
          </PanelSectionRow>
          {!busy && (
            <PanelSectionRow>
              <ButtonItem layout="below" disabled={running} onClick={updateAllNow}>
                {running ? "Updating…" : "Update All"}
              </ButtonItem>
            </PanelSectionRow>
          )}
        </>
      )}
      {!gettingStarted && (
        <InstallMoreButton backends={backends} helix={helix} refresh={onUpdated} markDone={markSetupDone} />
      )}
      <PanelSectionRow>
        <ToggleField
          label="Show backends"
          checked={!collapsed}
          onChange={onToggle}
          description={
            collapsed
              ? helix?.job?.state === "failed"
                ? `HelixSR ${helix.job.tag} setup failed: show backends to try again.`
                : undefined
              : "Shown at the bottom, below the game."
          }
        />
      </PanelSectionRow>
    </PanelSection>
    </>
  );
}

// The backends themselves (installs, updates, setup), at the bottom of the panel while Show backends is on
export function BackendsSection(props: Props) {
  const {
    backends,
    helix,
    onHelixChange,
    opti,
    onOptiChange,
    onMakoChange,
    fsr4,
    onFsr4Change,
    anr,
    onAnrChange,
  } = props;
  const version = usePluginVersion();
  return (
    <PanelSection title="Backends">
      <PanelSectionRow>
        <Field label="MultiFrameGen" bottomSeparator="standard">
          {version ?? "…"}
        </Field>
      </PanelSectionRow>
      <UpdatesCheck
        optiJobState={opti?.job?.state}
        helixJobState={helix?.job?.state}
        onOptiChange={onOptiChange}
        onHelixChange={onHelixChange}
        onMakoChange={onMakoChange}
        fsr4JobState={fsr4?.job?.state}
        onFsr4Change={onFsr4Change}
        anrJobState={anr?.job?.state}
        onAnrChange={onAnrChange}
      />
      {backends === null ? (
        <PanelSectionRow>
          <Field label="Checking…" />
        </PanelSectionRow>
      ) : (
        backends.map((b) => (
          <div key={b.id}>
            <PanelSectionRow>
              {/* the status goes in the label: a value on the right would squeeze the description into the left
                  column (FSR4 Injector's long one wrapped at half width) */}
              <Field
                label={`${b.name} · ${statusLine(b)}`}
                description={[b.kind, ...(b.notes ?? [])].join("\n")}
                bottomSeparator="standard"
              />
            </PanelSectionRow>
            {b.id === "helixsr" && (
              <HelixSRSetup status={helix} onChange={onHelixChange} />
            )}
            {b.id === "optiscaler" && (
              <OptiScalerSetup status={opti} onChange={onOptiChange} />
            )}
            {b.id === "fsr4injector" && (
              <Fsr4Setup status={fsr4} onChange={onFsr4Change} />
            )}
            {b.id === "anrfg" && (
              <AnrSetup status={anr} onChange={onAnrChange} />
            )}
            {b.id === "mako" && (
              <MakoInstall
                installed={b.installed}
                rendererMissing={b.installed && b.renderer_installed === false}
                onChange={onMakoChange}
              />
            )}
          </div>
        ))
      )}
    </PanelSection>
  );
}

// MAKO's own install (the MAKO Renderer, downloaded from MAKO's releases); its controls appear for games set to MAKO
// asked once per Steam session, not every time the panel opens
let rendererPrompted = false;

function MakoInstall({
  installed,
  rendererMissing,
  onChange,
}: {
  installed: boolean;
  rendererMissing: boolean;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const toast = (body: string) => toaster.toast({ title: "MAKO", body });
  const install = async () => {
    setBusy(true);
    try {
      const r = await installMako();
      if (r.success) promptRestart("MAKO");
      else toast(r.error || "Install failed");
    } finally {
      setBusy(false);
      onChange();
    }
  };
  useEffect(() => {
    if (!rendererMissing || rendererPrompted) return;
    rendererPrompted = true;
    showModal(
      <ConfirmModal
        strTitle="Install the MAKO Renderer"
        strDescription="MAKO is set up, but the MAKO Renderer it runs games with isn't installed. Games set to MAKO won't start with MAKO until it is. Install it now?"
        strOKButtonText="Install"
        strCancelButtonText="Later"
        onOK={install}
      />,
    );
  }, [rendererMissing]);
  // MAKO's launcher comes out of the games' launch options first: a game would not start with it missing
  const uninstall = async () => {
    setBusy(true);
    try {
      let failed = 0;
      for (const appid of await makoGames()) {
        const id = Number(appid);
        const current = await readLaunchOptions(id);
        if (current === null) {
          failed++;
          continue;
        }
        const r = await makoGameLaunchOptions(current, false);
        if (
          r.ok &&
          r.launch_options !== undefined &&
          r.launch_options !== current &&
          !writeLaunchOptions(id, r.launch_options)
        ) {
          failed++;
        }
      }
      const r = await uninstallMako();
      toast(
        !r.success
          ? r.error || "Uninstall failed"
          : failed
            ? `Removed. ${failed} game(s) still have MAKO's launcher in their launch options: remove it in Steam.`
            : "Removed. MAKO's launcher was taken out of your games' launch options.",
      );
    } finally {
      setBusy(false);
      onChange();
    }
  };
  const confirm = () =>
    showModal(
      <ConfirmModal
        strTitle="Uninstall MAKO"
        strDescription="Removes the MAKO Renderer and takes MAKO's launcher out of the launch options of games set to MAKO. Their MAKO choice stays: after reinstalling, add the launcher back from the game's MAKO panel."
        strOKButtonText="Uninstall"
        onOK={uninstall}
      />,
    );
  return (
    <>
      {rendererMissing && (
        <>
          <PanelSectionRow>
            <Field
              label="MAKO Renderer isn't installed"
              description="Games set to MAKO need it to start with MAKO."
            />
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={install}>
              {busy ? "Installing the MAKO Renderer…" : "Install MAKO Renderer"}
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy}
          onClick={installed ? confirm : install}
        >
          {busy
            ? installed
              ? "Uninstalling MAKO…"
              : "Installing MAKO…"
            : installed
              ? "Uninstall MAKO"
              : "Install MAKO"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
