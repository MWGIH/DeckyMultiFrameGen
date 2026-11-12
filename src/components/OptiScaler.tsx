import { useEffect, useRef, useState } from "react";
import { OptiLog } from "./OptiLog";
import { BelowDropdown } from "./BelowDropdown";
import { ButtonItem, ConfirmModal, Field, PanelSectionRow, showModal } from "@decky/ui";
import { ProgressRow } from "./ProgressRow";
import { toaster } from "@decky/api";
import {
  optiscalerGameStatus,
  optiscalerInstall,
  optiscalerPatchGame,
  optiscalerFsr4Files,
  optiscalerStatus,
  optiscalerUninstall,
  type OptiFsr4Files,
  type OptiFsr4State,
  type OptiGame,
  type OptiStatus,
} from "../api";
import { defaultProxyDll, PROXY_DLL_OPTIONS } from "../optiscalerOptions";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

const POLL_MS = 5000;

// The FSR 4 files a game's OptiScaler is patched with (per game)
const FSR4_FILES: { value: OptiFsr4Files; label: string; hint: string }[] = [
  {
    value: "deck",
    label: "FSR 4.1.1 Deck build (Valve)",
    hint: "The default: Valve's FSR 4.1.1 build for the Steam Deck's RDNA 2 GPU, with its own amdxc64.dll.",
  },
  {
    value: "lite",
    label: "FSR 4.1.2 Lite (AMD)",
    hint: "AMD's smaller FSR 4 model made for handheld chips, usually faster than the full model. The first time, AMD's FSR 4.1.2 file (about 43 MB) is downloaded from AMD's own driver installer, which means you accept AMD's software licence, and a newer OptiScaler build (about 70 MB) from OptiScaler's GitHub. DirectX 12 games.",
  },
  {
    value: "lossy",
    label: "FSR 4.1.2 Lossy (Cyboman)",
    hint: "Cyboman's lossy FSR 4.1.2 build for Steam Deck / RDNA2 iGPUs: about 30% faster than the Valve Deck build by skipping the network on some frames; picture is close to AMD's, not identical. Downloaded on first use (about 9 MB). Single-player only.",
  },
  {
    value: "lite-lossy",
    label: "FSR 4.1.2 Lite Lossy (Cyboman)",
    hint: "Cyboman's lossy FSR 4.1.2 Lite build for Steam Deck / RDNA2 iGPUs: about 13–22% faster than AMD Lite; picture is close to Lite's, not identical. Single-player only.",
  },
  {
    value: "plain",
    label: "Without the FSR 4.1 Deck files",
    hint: "For a game that won't start with OptiScaler: stock OptiScaler 0.9.4 with FSR 4.0.2.",
  },
];
const POLL_RUNNING_MS = 1000;

function toast(body: string) {
  toaster.toast({ title: "OptiScaler", body });
}

export function useOptiStatus() {
  const [status, setStatus] = useState<OptiStatus | null>(null);
  const running = status?.job?.state === "running";
  const wasRunning = useRef(false);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      optiscalerStatus()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    load();
    const id = setInterval(load, running ? POLL_RUNNING_MS : POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [running]);
  useEffect(() => {
    const job = status?.job;
    if (wasRunning.current && job && job.state !== "running") {
      toast(job.message ?? (job.state === "done" ? "Installed" : "Install failed"));
    }
    wasRunning.current = running;
  }, [status?.job?.state]);
  return [status, setStatus] as const;
}

const MB = 1024 * 1024;

// Installing OptiScaler into ~/fgmod, the way Decky Framegen does (and where it finds an install Decky Framegen made).
export function OptiScalerSetup({ status, onChange }: { status: OptiStatus | null; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  if (!status) return null;

  const install = async () => {
    setBusy(true);
    try {
      const r = await optiscalerInstall();
      if (r.status !== "started") toast(r.message ?? "Install failed");
    } finally {
      setBusy(false);
      onChange();
    }
  };

  const job = status.job;
  if (job?.state === "running") {
    const progress = job.phase === "download" && job.size ? Math.min(1, job.downloaded / job.size) : undefined;
    return (
      <ProgressRow
        title="Installing OptiScaler"
        percent={progress === undefined ? undefined : progress * 100}
        detail={
          job.phase === "download"
            ? `Downloading ${job.asset ?? ""} (${Math.round(job.downloaded / MB)} of ${Math.round(job.size / MB)} MB)`
            : "Unpacking into ~/fgmod"
        }
      />
    );
  }

  const uninstall = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove OptiScaler"
        strDescription="Removes OptiScaler's files from ~/fgmod. Set your games' Use to something else first: patched games keep their copy until you do."
        strOKButtonText="Remove"
        onOK={async () => {
          setBusy(true);
          try {
            const r = await optiscalerUninstall();
            toast(r.status === "success" ? "Removed" : r.message ?? "Removing failed");
          } finally {
            setBusy(false);
            onChange();
          }
        }}
      />,
    );

  return (
    <>
      {job?.state === "failed" && (
        <PanelSectionRow>
          <Field label="OptiScaler install failed" description={job.message ?? undefined} />
        </PanelSectionRow>
      )}
      {status.legacy && (
        <PanelSectionRow>
          <Field
            label="Older OptiScaler install found"
            description="~/fgmod is from an earlier Decky Framegen and lacks files this plugin needs. Update it to patch games from here."
          />
        </PanelSectionRow>
      )}
      {!status.exists && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={install}>
            {busy ? "Starting…" : status.legacy ? "Update OptiScaler" : "Install OptiScaler"}
          </ButtonItem>
        </PanelSectionRow>
      )}
      {status.exists && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={uninstall}>
            Remove OptiScaler
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}

export function OptiScalerGame({
  appid,
  status,
  onChange,
  running = false,
  autoPatch = true,
  refresh = 0,
}: {
  appid: string;
  status: OptiStatus | null;
  onChange?: () => void;
  // the game is running: patching swaps files it has open, so the proxy DLL waits until it's closed
  running?: boolean;
  // patch the game with its proxy DLL by itself when it's set to OptiScaler but isn't patched
  autoPatch?: boolean;
  // bumped when the game's Use changed, to read its OptiScaler state again
  refresh?: number;
}) {
  const [game, setGame] = useState<OptiGame | null>(null);
  const [dll, setDll] = useState<string>(defaultProxyDll(appid));
  const [busy, setBusy] = useState(false);
  const [fsr4, setFsr4] = useState<OptiFsr4State | null>(null);
  const fsr4Files: OptiFsr4Files = fsr4?.files ?? "deck";
  const fsr4Options = FSR4_FILES.filter((o) => !fsr4 || fsr4.options.includes(o.value));
  const liteNote = fsr4?.lite_unfit && !fsr4.options.includes("lite")
    ? ` FSR 4.1.2 Lite options aren't offered here: they ${fsr4.lite_unfit}.`
    : "";
  // the game this panel already patched by itself, so a failed patch isn't retried over and over
  const autoTried = useRef<string | null>(null);

  const load = () =>
    optiscalerGameStatus(appid).then((g) => {
      setGame(g);
      setDll(g.dll_name || defaultProxyDll(appid));
      return g;
    });
  useEffect(() => {
    setGame(null);
    load();
    setFsr4(null);
    optiscalerFsr4Files(appid).then(setFsr4);
  }, [appid]);
  useEffect(() => {
    if (refresh) load();
  }, [refresh]);

  const id = Number(appid);
  // Choosing Use patches the game; this patches it again with another proxy DLL, or when that didn't happen
  const patch = async (dllName: string, why: string) => {
    if (running) {
      toast("Close the game before patching it.");
      return;
    }
    setBusy(true);
    const name = game?.name ?? "the game";
    toast(`${why} Patching ${name} with OptiScaler (${dllName}). Please wait before starting the game.`.trim());
    try {
      const current = (await readLaunchOptions(id)) ?? "";
      const r = await optiscalerPatchGame(appid, dllName, current);
      if (r.status === "success") {
        if (r.launch_options && !writeLaunchOptions(id, r.launch_options)) {
          toast(`Patched, but couldn't set the launch options. Set them in Steam: ${r.launch_options}`);
        } else {
          const removed = r.removed?.length ? `Removed ${r.removed.join(" and ")}. ` : "";
          toast(`${removed}${r.message ?? "Patched"} In the game, select DLSS to get FSR / XeSS. Insert opens OptiScaler's menu.`);
        }
        if (r.helix_in_opti && !r.helix_in_opti.ok) toast(`HelixSR wasn't added: ${r.helix_in_opti.error}`);
        toast(`${name} is ready. You can start the game now.`);
      } else {
        toast(r.message ?? "Patching failed");
      }
    } finally {
      setBusy(false);
      load();
      onChange?.();
    }
  };

  // Set to OptiScaler but not patched (e.g. a game update put its own files back): patch it with the default proxy DLL
  useEffect(() => {
    if (!game || game.patched || !game.install_found || !status?.exists || !autoPatch || running || busy) return;
    if (autoTried.current === appid) return;
    autoTried.current = appid;
    patch(game.dll_name || defaultProxyDll(appid), "OptiScaler isn't in this game yet.");
  }, [game, status?.exists, autoPatch, running]);

  if (!status?.exists) {
    return (
      <PanelSectionRow>
        <Field label="OptiScaler" description="Install OptiScaler below first." />
      </PanelSectionRow>
    );
  }
  if (!game) {
    return (
      <PanelSectionRow>
        <Field label="Checking the game for OptiScaler…" />
      </PanelSectionRow>
    );
  }

  const changeDll = (dllName: string) => {
    if (dllName === dll && game.patched) return;
    setDll(dllName);
    patch(dllName, "");
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label={busy ? "Patching OptiScaler…" : game.patched ? "OptiScaler patched" : "OptiScaler not patched"}
          description={
            game.patched
              ? `${game.message ?? ""} In the game, select DLSS to get FSR / XeSS. Insert opens OptiScaler's menu.`
              : running
                ? `${game.message ?? ""} Close the game and it's patched by itself.`.trim()
                : `${game.message ?? ""} Patching didn't work: try another proxy DLL below, or patch again.`.trim()
          }
        />
      </PanelSectionRow>
      {busy && (
        <ProgressRow
          title={`Patching OptiScaler (${dll}), please wait…`}
          detail="Don't start the game until this is done."
        />
      )}
      <PanelSectionRow>
        <Field
          label="Tip: bind Insert to a back button"
          description="OptiScaler's menu opens with the keyboard's Insert key. In the game's controller settings (Steam button, then Controller), set a back button (L4, L5, R4 or R5) to the keyboard key Insert to open the menu in game."
        />
      </PanelSectionRow>
      {game.patched && <OptiLog appid={appid} />}
      <PanelSectionRow>
        <BelowDropdown
          label="Proxy DLL"
          description={`${PROXY_DLL_OPTIONS.find((o) => o.value === dll)?.hint ?? ""}${running ? " Close the game to change it." : " Changing it patches the game again."}`}
          rgOptions={PROXY_DLL_OPTIONS.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={dll}
          disabled={busy || running}
          onChange={(o) => changeDll(String(o.data))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <BelowDropdown
          label="FSR 4 files"
          description={`${FSR4_FILES.find((o) => o.value === fsr4Files)?.hint ?? ""}${liteNote}${running ? " Close the game to change it." : " Changing it patches the game again."}`}
          rgOptions={fsr4Options.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={fsr4Files}
          disabled={busy || running}
          onChange={async (o) => {
            const r = await optiscalerFsr4Files(appid, o.data as OptiFsr4Files);
            setFsr4(r);
            if (!r.ok) {
              toast(r.error ?? "Couldn't change the FSR 4 files");
              return;
            }
            patch(dll, "");
          }}
        />
      </PanelSectionRow>
      {!game.patched && !busy && !running && (
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={() => patch(dll, "")}>
            Patch again
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
