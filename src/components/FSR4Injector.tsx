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
  fsr4CompatibleGames,
  fsr4Details,
  fsr4GameOff,
  fsr4GameOn,
  fsr4Games,
  fsr4GameStatus,
  fsr4Install,
  fsr4Remove,
  fsr4Status,
  fsr4Watermark,
  type Fsr4Details,
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
  if (!status) return <FullDetails status={status} onChange={onChange} />;

  const job = status.job;
  if (job?.state === "running") {
    const progress =
      job.phase === "amd" && job.total ? Math.min(1, job.done / job.total) : undefined;
    return (
      <>
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
      <FullDetails status={status} onChange={onChange} />
      </>
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
      <FullDetails status={status} onChange={onChange} />
    </>
  );
}

// "Show all FSR4 Injector settings": the toggle at the bottom of FSR4 Injector (in Backends and in the game's panel)
// that opens its full panel; remembered across both places
function FullDetails({
  status,
  onChange,
}: {
  status: Fsr4Status | null;
  onChange: () => void;
}) {
  const [full, setFullState] = useState(readFull);
  const setFull = (on: boolean) => {
    setFullState(on);
    try {
      localStorage.setItem(FULL_KEY, on ? "1" : "0");
    } catch {
      // just not remembered
    }
  };
  return (
    <>
      <PanelSectionRow>
        <ToggleField
          label="Show all FSR4 Injector settings"
          description={full ? undefined : "Version, GPU, AMD's library, launch options, and every game it is in or can go in."}
          checked={full}
          onChange={setFull}
        />
      </PanelSectionRow>
      {full &&
        (status ? (
          <Fsr4FullPanel status={status} onChange={onChange} />
        ) : (
          <PanelSectionRow>
            <Field label="Loading FSR4 Injector's details…" />
          </PanelSectionRow>
        ))}
    </>
  );
}

const FULL_KEY = "multifg:fsr4Full";

function readFull(): boolean {
  try {
    return localStorage.getItem(FULL_KEY) === "1";
  } catch {
    return false;
  }
}

// FSR4 Injector's own panel, all of it: its version, the GPU, AMD's library, the launch options it uses, the games it
// is in with their last session, and the games it could go in
function Fsr4FullPanel({
  status,
  onChange,
}: {
  status: Fsr4Status;
  onChange: () => void;
}) {
  const [d, setD] = useState<Fsr4Details | null>(null);
  const [compatible, setCompatible] = useState<
    Awaited<ReturnType<typeof fsr4CompatibleGames>> | null
  >(null);
  const [scanning, setScanning] = useState(false);
  useEffect(() => {
    fsr4Details().then(setD);
  }, [status.version, status.ready, status.games.join(",")]);

  const scan = async () => {
    setScanning(true);
    try {
      setCompatible(await fsr4CompatibleGames());
    } finally {
      setScanning(false);
    }
  };
  const update = async () => {
    const r = await fsr4Install();
    if (!r.ok) toast(r.error ?? "Couldn't start");
    onChange();
  };

  if (!d) {
    return (
      <PanelSectionRow>
        <Field label="Loading FSR4 Injector's details…" />
      </PanelSectionRow>
    );
  }
  if (!d.ok || !d.unpacked) {
    return (
      <PanelSectionRow>
        <Field
          label="FSR4 Injector isn't installed"
          description={d.error ?? "Install it above to see its details."}
        />
      </PanelSectionRow>
    );
  }
  const gpu = d.gpu;
  const row = (key: string, label: string, description: string) => (
    <PanelSectionRow key={key}>
      <Field label={label} description={description} />
    </PanelSectionRow>
  );
  return (
    <>
      {row("v", `FSR4 Injector ${d.version ?? ""}`, `From github.com/Rayekkk/FSR4Injector, in ${d.folder}`)}
      {row(
        "g",
        "GPU",
        gpu
          ? [
              `${gpu.arch}${gpu.pci ? ` (PCI ${gpu.pci}, family ${gpu.family}, revision ${gpu.rev})` : ""}`,
              gpu.model
                ? `FSR 4 model: ${gpu.model_name}${gpu.verified ? "" : " (beta: not yet confirmed on this GPU by FSR4 Injector's author)"}`
                : "AMD's FSR 4 has no model for this GPU: games stay on FSR 3",
            ].join("\n")
          : "No AMD GPU found",
      )}
      {d.amd &&
        row(
          "a",
          "AMD's FSR 4 library",
          `FSR ${d.amd.fsr} (amdxcffx64.dll ${d.amd.file_version}, ${d.amd.size_mb} MB) from AMD ${d.amd.driver}.\n${d.amd.ready ? `Downloaded and checked: ${d.amd.path}` : "Not downloaded yet"}`,
        )}
      {d.launch_options &&
        row(
          "l",
          "Launch options it sets",
          `${d.launch_options.plain}\nWith the watermark: ${d.launch_options.watermark}`,
        )}
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={update}>
          Update or repair FSR4 Injector
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
      {row(
        "gh",
        `Games with FSR4 Injector (${d.games?.length ?? 0})`,
        d.games?.length
          ? "Its result from each game's last session:"
          : "None yet: set a game's Use to FSR4 Injector.",
      )}
      {(d.games ?? []).map((g) =>
        row(
          `g${g.appid}`,
          g.name,
          `${VERDICTS[g.verdict] ?? g.verdict}. ${g.reason}${g.watermark ? " Watermark on." : ""}`,
        ),
      )}
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={scanning} onClick={scan}>
          {scanning ? "Looking through your games…" : "Find games with FSR 3.1+"}
        </ButtonItem>
      </PanelSectionRow>
      {compatible &&
        (compatible.games.length
          ? compatible.games.map((g) =>
              row(
                `c${g.appid}`,
                g.name,
                `${g.enabled ? "FSR4 Injector is in it." : "Set its Use to FSR4 Injector to turn it on."} Ships ${g.ffx_dll}.${g.anticheat ? " ⚠️ Has anti-cheat: online bans are possible." : ""}`,
              ),
            )
          : row(
              "cn",
              "No compatible games found",
              compatible.error ??
                "None of your installed games ships an FSR 3.1+ DLL (DirectX 12).",
            ))}
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
  onChange,
}: {
  appid: string;
  status: Fsr4Status | null;
  onChange?: () => void;
}) {
  const [game, setGame] = useState<Fsr4Game | null>(null);
  const [busy, setBusy] = useState(false);
  const [watermarkOn, setWatermarkOn] = useState(false);
  const ready = Boolean(status?.ready);
  const load = () =>
    fsr4GameStatus(appid).then((g) => {
      setGame(g);
      if (g.watermark !== undefined) setWatermarkOn(g.watermark);
    });
  useEffect(() => {
    setGame(null);
    load(); // also before it's installed: the watermark choice is kept per game
  }, [appid, ready]);

  // why FSR4 Injector can't go in yet, if it can't; the watermark and full settings show either way
  const blocked: { label: string; description?: string } | null = !ready
    ? {
        label: "FSR4 Injector isn't installed",
        description: status?.unpacked
          ? "Download AMD's FSR 4 library under Backends, FSR4 Injector."
          : "Install it under Backends, FSR4 Injector.",
      }
    : !game
      ? { label: "Checking the game for FSR 3.1…" }
      : !game.ok
        ? { label: "FSR4 Injector", description: game.error }
        : !game.found
          ? {
              label: "FSR4 Injector can't be used here",
              description:
                "This game has no FSR 3.1 DLL (amd_fidelityfx_dx12.dll, amd_fidelityfx_upscaler_dx12.dll or amd_fidelityfx_loader_dx12.dll). FSR4 Injector only works in DirectX 12 games with FSR 3.1 or newer; FSR 2, FSR 3.0 and Vulkan games aren't supported.",
            }
          : null;

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
    setWatermarkOn(on);
    const current = (await readLaunchOptions(Number(appid))) ?? "";
    const r = await fsr4Watermark(appid, on, current);
    if (r.ok) applyLaunchOptions(appid, current, r.launch_options);
    else toast(r.error ?? "Couldn't change the watermark");
    if (ready) load();
  };

  const watermarkToggle = (
    <PanelSectionRow>
      <ToggleField
        label="Show AMD's FSR 4 watermark"
        description="AMD's library draws which FSR 4 model runs, so you can see FSR 4 is working. Adds FSR_WATERMARK=1 to the launch options."
        checked={watermarkOn}
        disabled={busy}
        onChange={watermark}
      />
    </PanelSectionRow>
  );
  const full = <FullDetails status={status} onChange={onChange ?? (() => undefined)} />;

  if (blocked || !game) {
    return (
      <>
        <PanelSectionRow>
          <Field label={blocked?.label} description={blocked?.description} />
        </PanelSectionRow>
        {watermarkToggle}
        {full}
      </>
    );
  }

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
      {watermarkToggle}
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
      {full}
    </>
  );
}
