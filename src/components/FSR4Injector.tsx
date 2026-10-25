import { useEffect, useRef, useState } from "react";
import {
  ButtonItem,
  ConfirmModal,
  Field,
  Navigation,
  PanelSectionRow,
  ProgressBarWithInfo,
  showModal,
  ToggleField,
} from "@decky/ui";
import { toaster } from "@decky/api";
import {
  fsr4GameOff,
  fsr4GameOn,
  fsr4Games,
  fsr4GameStatus,
  fsr4Install,
  fsr4Remove,
  fsr4Status,
  fsr4Watermark,
  type Fsr4Game,
  type Fsr4Status,
} from "../api";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

const POLL_RUNNING_MS = 1000;
const POLL_IDLE_MS = 10000;
const MB = 1024 * 1024;

function toast(body: string) {
  toaster.toast({ title: "FSR4 Injector", body });
}

export function useFsr4Status() {
  const [status, setStatus] = useState<Fsr4Status | null>(null);
  const running = status?.job?.state === "running";
  const wasRunning = useRef(false);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      fsr4Status()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    load();
    const id = setInterval(load, running ? POLL_RUNNING_MS : POLL_IDLE_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [running]);
  useEffect(() => {
    const job = status?.job;
    if (wasRunning.current && job && job.state !== "running")
      toast(
        job.state === "done"
          ? `FSR4 Injector ${job.version ?? ""} is ready. Set a game to it under Use.`
          : (job.error ?? "Install failed"),
      );
    wasRunning.current = running;
  }, [status?.job?.state]);
  return [status, setStatus] as const;
}

// Writes the launch options a call returned; says what to set by hand when Steam doesn't take them
function applyLaunchOptions(
  appid: string,
  current: string,
  next: string | null | undefined,
): boolean {
  if (next == null || next === current) return true;
  if (writeLaunchOptions(Number(appid), next)) return true;
  toast(`Couldn't set the launch options. Set them in Steam: ${next || "(empty)"}`);
  return false;
}

// Takes FSR4 Injector out of every game it is in, launch options included; returns how many couldn't be changed
export async function fsr4OffEverywhere(): Promise<number> {
  let failed = 0;
  for (const appid of await fsr4Games()) {
    const current = await readLaunchOptions(Number(appid));
    if (current === null) {
      failed++;
      continue;
    }
    const r = await fsr4GameOff(appid, current);
    if (!r.ok || !applyLaunchOptions(appid, current, r.launch_options))
      failed++;
  }
  return failed;
}

function gpuProblem(status: Fsr4Status): string | null {
  if (!status.unpacked) return null;
  if (!status.gpu)
    return "No AMD GPU was found, or its details couldn't be read, so FSR 4 can't run here.";
  if (!status.gpu.model)
    return `AMD's FSR 4 has no model for this GPU (${status.gpu.arch}), so games would stay on FSR 3.`;
  return null;
}

// In Backends: FSR4 Injector's release from GitHub, then AMD's FSR 4 library from AMD
export function Fsr4Setup({
  status,
  onChange,
}: {
  status: Fsr4Status | null;
  onChange: () => void;
}) {
  const [busy, setBusy] = useState(false);
  if (!status) return null;

  const job = status.job;
  if (job?.state === "running") {
    const progress =
      job.phase === "amd" && job.total ? Math.min(1, job.done / job.total) : undefined;
    return (
      <PanelSectionRow>
        <ProgressBarWithInfo
          label="Installing FSR4 Injector"
          description={
            job.phase === "amd"
              ? `Fetching AMD's FSR 4 library from AMD (${Math.round(job.done / MB)} of ${Math.round(job.total / MB)} MB)`
              : `Downloading FSR4 Injector ${job.version ?? ""} from GitHub`
          }
          nProgress={progress === undefined ? undefined : progress * 100}
          indeterminate={progress === undefined}
          sOperationText={
            progress === undefined ? undefined : `${Math.round(progress * 100)}%`
          }
        />
      </PanelSectionRow>
    );
  }

  const install = async () => {
    setBusy(true);
    try {
      const r = await fsr4Install();
      if (!r.ok) toast(r.error ?? "Install failed");
    } finally {
      setBusy(false);
      onChange();
    }
  };
  const askInstall = () =>
    showModal(
      <ConfirmModal
        strTitle="Install FSR4 Injector"
        strDescription={`Downloads FSR4 Injector from its GitHub releases, then AMD's FSR 4 library (FSR ${status.recipe?.fsr ?? "4"}) straight from AMD's driver package on AMD's servers: about 43 MB. AMD's library is covered by the AMD Software End User License Agreement; installing means you accept it.`}
        strOKButtonText="Accept and install"
        onOK={install}
      />,
    );

  const remove = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove FSR4 Injector"
        strDescription="Takes FSR4 Injector out of every game it is in (their launch options go back too), then deletes its files and AMD's library. Games set to it keep that choice: they run with their own FSR until you install it again."
        strOKButtonText="Remove"
        onOK={async () => {
          setBusy(true);
          try {
            const failed = await fsr4OffEverywhere();
            const r = await fsr4Remove();
            toast(
              !r.ok
                ? (r.error ?? "Removing failed")
                : failed
                  ? `Removed. ${failed} game(s) still have WINEDLLOVERRIDES=amdxc64=n,b in their launch options: remove it in Steam.`
                  : "Removed, and taken out of your games.",
            );
          } finally {
            setBusy(false);
            onChange();
          }
        }}
      />,
    );

  const gpu = gpuProblem(status);
  return (
    <>
      {job?.state === "failed" && (
        <PanelSectionRow>
          <Field label="FSR4 Injector install failed" description={job.error ?? undefined} />
        </PanelSectionRow>
      )}
      {gpu && (
        <PanelSectionRow>
          <Field label="⚠️ FSR 4 can't run on this GPU" description={gpu} />
        </PanelSectionRow>
      )}
      {!status.ready && (
        <>
          <PanelSectionRow>
            <ButtonItem layout="below" disabled={busy} onClick={askInstall}>
              {status.unpacked ? "Download AMD's FSR 4 library" : "Install FSR4 Injector"}
            </ButtonItem>
          </PanelSectionRow>
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => Navigation.NavigateToExternalWeb(status.eula_url)}
            >
              Read AMD's license
            </ButtonItem>
          </PanelSectionRow>
        </>
      )}
      {(status.unpacked || status.ready) && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={remove}>
            Remove FSR4 Injector
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}

const VERDICTS: Record<string, string> = {
  ok: "✓ FSR 4 active",
  unused: "FSR wasn't used last session",
  failed: "⚠️ FSR 4 not active",
  unknown: "FSR4 Injector is on: not checked yet",
};

// In the game's panel for the choices with FSR4 Injector
export function Fsr4Game({
  appid,
  status,
}: {
  appid: string;
  status: Fsr4Status | null;
}) {
  const [game, setGame] = useState<Fsr4Game | null>(null);
  const [busy, setBusy] = useState(false);
  const ready = Boolean(status?.ready);
  const load = () => fsr4GameStatus(appid).then(setGame);
  useEffect(() => {
    setGame(null);
    if (ready) load();
  }, [appid, ready]);

  if (!ready) {
    return (
      <PanelSectionRow>
        <Field
          label="FSR4 Injector"
          description={
            status?.unpacked
              ? "Download AMD's FSR 4 library under Backends first."
              : "Install FSR4 Injector under Backends first."
          }
        />
      </PanelSectionRow>
    );
  }
  if (!game) {
    return (
      <PanelSectionRow>
        <Field label="Checking the game for FSR 3.1…" />
      </PanelSectionRow>
    );
  }
  if (!game.ok) {
    return (
      <PanelSectionRow>
        <Field label="FSR4 Injector" description={game.error} />
      </PanelSectionRow>
    );
  }
  if (!game.found) {
    return (
      <PanelSectionRow>
        <Field
          label="FSR4 Injector can't be used here"
          description="This game has no FSR 3.1 DLL (amd_fidelityfx_dx12.dll, amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_loader_dx12.dll). FSR4 Injector only works in DirectX 12 games with FSR 3.1 or newer; FSR 2, FSR 3.0 and Vulkan games aren't supported."
        />
      </PanelSectionRow>
    );
  }

  const change = async (on: boolean) => {
    setBusy(true);
    try {
      const current = await readLaunchOptions(Number(appid));
      if (current === null) return toast("Couldn't read the game's launch options.");
      const r = on ? await fsr4GameOn(appid, current) : await fsr4GameOff(appid, current);
      if (!r.ok) return toast(r.error ?? "That didn't work");
      applyLaunchOptions(appid, current, r.launch_options);
      toast(
        on
          ? "On. Start the game and choose AMD FSR as its upscaler."
          : "Taken out of the game. Its launch options are back.",
      );
    } finally {
      setBusy(false);
      load();
    }
  };

  const watermark = async (on: boolean) => {
    const current = (await readLaunchOptions(Number(appid))) ?? "";
    const r = await fsr4Watermark(appid, on, current);
    if (r.ok) applyLaunchOptions(appid, current, r.launch_options);
    else toast(r.error ?? "Couldn't change the watermark");
    load();
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label={
            game.enabled
              ? (VERDICTS[game.verdict ?? "unknown"] ?? VERDICTS.unknown)
              : "FSR4 Injector isn't in this game"
          }
          description={
            game.enabled
              ? `${game.reason ?? ""} In the game, choose AMD FSR as the upscaler.`.trim()
              : `Puts AMD's FSR 4 library next to the game's ${game.ffx_dll ?? "FSR 3.1 DLL"}, so the game's AMD FSR option runs FSR 4.`
          }
        />
      </PanelSectionRow>
      {game.anticheat && (
        <PanelSectionRow>
          <Field
            label="⚠️ Anti-cheat found"
            description="Adding DLLs to a game's folder can get you kicked or banned in online games. Use FSR4 Injector here at your own risk."
          />
        </PanelSectionRow>
      )}
      <PanelSectionRow>
        <ToggleField
          label="Show AMD's FSR 4 watermark"
          description="AMD's library draws which FSR 4 model runs, so you can see FSR 4 is working. Adds FSR_WATERMARK=1 to the launch options."
          checked={!!game.watermark}
          disabled={busy}
          onChange={watermark}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          disabled={busy || (!game.enabled && !game.gpu_supported)}
          onClick={() => change(!game.enabled)}
        >
          {game.enabled
            ? "Take FSR4 Injector out of this game"
            : game.gpu_supported
              ? "Put FSR4 Injector in this game"
              : "FSR 4 has no model for this GPU"}
        </ButtonItem>
      </PanelSectionRow>
    </>
  );
}
