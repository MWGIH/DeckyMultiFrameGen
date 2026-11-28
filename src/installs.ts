import { useEffect, useState } from "react";
import { anrInstall, fsr4Install, helixsrInstall, helixsrSetBuild, optiscalerInstall } from "./api";
import { installMako } from "./mako/api/makoApi";
import type { BatchName } from "./updateProgress";
import { toaster } from "@decky/api";
import { promptRestart } from "./restartPrompt";

// The backends a user installs, by the ids get_backends and the Use choices use
export type InstallId = "optiscaler" | "fsr4injector" | "helixsr" | "mako" | "anrfg";

export const INSTALL_NAMES: Record<InstallId, BatchName> = {
  optiscaler: "OptiScaler",
  fsr4injector: "FSR4 Injector",
  helixsr: "HelixSR",
  mako: "MAKO",
  anrfg: "ANR FG",
};

// The order they're offered and started in: the background jobs first, MAKO (which installs while it's waited for) last
export const INSTALL_ORDER: InstallId[] = ["optiscaler", "fsr4injector", "helixsr", "mako", "anrfg"];

export type Batch = {
  kind: "update" | "install";
  names: BatchName[];
  seen: BatchName[];
  at: number;
  // install: HelixSR's network is built (it then needs a restart, as MAKO does)
  helixBuild?: boolean;
  // install: what couldn't even start, for the one toast at the end
  startFailed?: string[];
  startFailedNames?: BatchName[];
  // install: called once everything has finished, with what failed (e.g. a Use choice waiting for it)
  after?: (failed: BatchName[]) => void;
};

const joinNames = (names: string[]) =>
  names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names[names.length - 1]}` : (names[0] ?? "");

// An install batch has finished (or only MAKO was installed, which is done when its call returns): one toast, one
// restart prompt for whatever needs it, then whatever waited for it
export function finishInstall(b: {
  names: BatchName[];
  failed: BatchName[];
  startFailed?: string[];
  helixBuild?: boolean;
  after?: (failed: BatchName[]) => void;
}) {
  const ok = b.names.filter((n) => !b.failed.includes(n));
  const parts: string[] = [];
  if (ok.length) parts.push(`${joinNames(ok)} ${ok.length > 1 ? "are" : "is"} installed.`);
  const notOk = b.names.filter((n) => b.failed.includes(n));
  if (notOk.length) parts.push(`${joinNames(notOk)} didn't install: show backends for what went wrong.`);
  if (b.startFailed?.length) parts.push(`Couldn't install ${b.startFailed.join("; ")}.`);
  if (parts.length) toaster.toast({ title: "MultiFrameGen", body: parts.join(" ") });
  const restart = ok.filter((n) => n === "MAKO" || (n === "HelixSR" && b.helixBuild !== false));
  if (restart.length) promptRestart(joinNames(restart), restart.length > 1);
  b.after?.(b.failed);
}

type State = { starting: string | null; batch: Batch | null };

// One state for the whole panel: the bar at the top shows updates and installs started anywhere
let state: State = { starting: null, batch: null };
const listeners = new Set<(s: State) => void>();

export function setInstallState(next: Partial<State>) {
  state = { ...state, ...next };
  listeners.forEach((l) => l(state));
}

export function getInstallState(): State {
  return state;
}

export function useInstallState(): State {
  const [s, set] = useState(state);
  useEffect(() => {
    listeners.add(set);
    set(state);
    return () => {
      listeners.delete(set);
    };
  }, []);
  return s;
}

// HelixSR's own "Restart to finish" prompt is held back while an install batch with it runs: one prompt comes at the end
let helixRestartHeld = false;
export function takeHelixRestartHeld(): boolean {
  const held = helixRestartHeld;
  helixRestartHeld = false;
  return held;
}

export type InstallRefresh = {
  opti: () => void;
  helix: () => void;
  mako: () => void;
  fsr4: () => void;
  anr: () => void;
};

export type InstallResult = {
  // background installs that started (their progress is in the batch), and MAKO when it installed
  started: BatchName[];
  failed: string[];
};

// Starts the installs: each backend's own install, the same as its button in Backends. HelixSR's Build HelixSR
// setting is written first, so its setup runs (or not) as chosen.
export async function installBackends(
  ids: InstallId[],
  opts: { helixBuild?: boolean; refresh: InstallRefresh; after?: (failed: BatchName[]) => void },
): Promise<InstallResult> {
  const { refresh } = opts;
  const started: BatchName[] = [];
  const failed: string[] = [];
  const failedNames: BatchName[] = [];
  const step = async (
    id: InstallId,
    work: () => Promise<{
      ok?: boolean;
      success?: boolean;
      status?: string;
      error?: string | null;
      message?: string | null;
    }>,
    after: () => void,
  ) => {
    const name = INSTALL_NAMES[id];
    setInstallState({ starting: id === "mako" ? "Installing MAKO" : `Starting ${name}` });
    try {
      const r = await work();
      if (r.ok ?? r.success ?? r.status !== "error") started.push(name);
      else {
        failed.push(`${name}: ${r.error || r.message || "failed"}`);
        failedNames.push(name);
      }
    } catch (e) {
      failed.push(`${name}: ${e}`);
      failedNames.push(name);
    } finally {
      after();
    }
  };
  const wanted = INSTALL_ORDER.filter((id) => ids.includes(id));
  if (wanted.includes("helixsr") && opts.helixBuild !== false) helixRestartHeld = true;
  try {
    for (const id of wanted) {
      if (id === "optiscaler") await step(id, () => optiscalerInstall(), refresh.opti);
      if (id === "fsr4injector") await step(id, fsr4Install, refresh.fsr4);
      if (id === "anrfg") await step(id, anrInstall, refresh.anr);
      if (id === "helixsr")
        await step(
          id,
          async () => {
            if (opts.helixBuild !== undefined) {
              const b = await helixsrSetBuild(opts.helixBuild);
              if (!b.ok) return b;
            }
            return helixsrInstall();
          },
          refresh.helix,
        );
      if (id === "mako") await step(id, installMako, refresh.mako);
    }
  } finally {
    setInstallState({ starting: null });
  }
  if (!started.includes("HelixSR")) helixRestartHeld = false;
  const background = started.filter((n) => n !== "MAKO");
  if (background.length)
    setInstallState({
      batch: {
        kind: "install",
        names: started,
        seen: [],
        at: Date.now(),
        helixBuild: opts.helixBuild,
        startFailed: failed,
        startFailedNames: failedNames,
        after: opts.after,
      },
    });
  else
    finishInstall({
      names: started,
      failed: failedNames,
      startFailed: failed,
      helixBuild: opts.helixBuild,
      after: opts.after,
    });
  return { started, failed };
}
