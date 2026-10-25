import { useEffect, useRef, useState } from "react";
import { OptiLog } from "./OptiLog";
import { ButtonItem, ConfirmModal, DropdownItem, Field, PanelSectionRow, ProgressBarWithInfo, showModal } from "@decky/ui";
import { toaster } from "@decky/api";
import {
  optiscalerGameStatus,
  optiscalerInstall,
  optiscalerPatchGame,
  optiscalerStatus,
  optiscalerUninstall,
  optiscalerUnpatchGame,
  type OptiGame,
  type OptiStatus,
} from "../api";
import { defaultProxyDll, PROXY_DLL_OPTIONS } from "../optiscalerOptions";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

const POLL_MS = 5000;
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
      <PanelSectionRow>
        <ProgressBarWithInfo
          label="Installing OptiScaler"
          description={
            job.phase === "download"
              ? `Downloading ${job.asset ?? ""} (${Math.round(job.downloaded / MB)} of ${Math.round(job.size / MB)} MB)`
              : "Unpacking into ~/fgmod"
          }
          nProgress={progress === undefined ? undefined : progress * 100}
          indeterminate={progress === undefined}
          sOperationText={progress === undefined ? undefined : `${Math.round(progress * 100)}%`}
        />
      </PanelSectionRow>
    );
  }

  const uninstall = () =>
    showModal(
      <ConfirmModal
        strTitle="Remove OptiScaler"
        strDescription="Removes OptiScaler's files from ~/fgmod. Unpatch your games first: patched games keep their copy until you do."
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
}: {
  appid: string;
  status: OptiStatus | null;
  onChange?: () => void;
}) {
  const [game, setGame] = useState<OptiGame | null>(null);
  const [dll, setDll] = useState<string>(defaultProxyDll(appid));
  const [busy, setBusy] = useState(false);

  const load = () =>
    optiscalerGameStatus(appid).then((g) => {
      setGame(g);
      setDll(g.dll_name || defaultProxyDll(appid));
    });
  useEffect(() => {
    setGame(null);
    load();
  }, [appid]);

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

  const id = Number(appid);
  const patch = async () => {
    setBusy(true);
    try {
      const current = (await readLaunchOptions(id)) ?? "";
      const r = await optiscalerPatchGame(appid, dll, current);
      if (r.status === "success") {
        if (r.launch_options && !writeLaunchOptions(id, r.launch_options)) {
          toast(`Patched, but couldn't set the launch options. Set them in Steam: ${r.launch_options}`);
        } else {
          const removed = r.removed?.length ? `Removed ${r.removed.join(" and ")}. ` : "";
          toast(`${removed}${r.message ?? "Patched"} In the game, select DLSS to get FSR / XeSS. Insert opens OptiScaler's menu.`);
        }
        if (r.helix_in_opti && !r.helix_in_opti.ok) toast(`HelixSR wasn't added: ${r.helix_in_opti.error}`);
      } else {
        toast(r.message ?? "Patching failed");
      }
    } finally {
      setBusy(false);
      load();
      onChange?.();
    }
  };

  const unpatch = async () => {
    setBusy(true);
    try {
      const r = await optiscalerUnpatchGame(appid);
      if (r.status === "success") {
        writeLaunchOptions(id, r.launch_options ?? "");
        toast(r.message ?? "Unpatched");
      } else {
        toast(r.message ?? "Unpatching failed");
      }
    } finally {
      setBusy(false);
      load();
      onChange?.();
    }
  };

  return (
    <>
      <PanelSectionRow>
        <Field
          label={game.patched ? "OptiScaler patched" : "OptiScaler not patched"}
          description={
            game.patched
              ? `${game.message ?? ""} In the game, select DLSS to get FSR / XeSS. Insert opens OptiScaler's menu.`
              : game.message
          }
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <Field
          label="Tip: bind Insert to a back button"
          description="OptiScaler's menu opens with the keyboard's Insert key. In the game's controller settings (Steam button, then Controller), set a back button (L4, L5, R4 or R5) to the keyboard key Insert to open the menu in game."
        />
      </PanelSectionRow>
      {game.patched && <OptiLog appid={appid} />}
      <PanelSectionRow>
        <DropdownItem
          label="Proxy DLL"
          description={PROXY_DLL_OPTIONS.find((o) => o.value === dll)?.hint}
          rgOptions={PROXY_DLL_OPTIONS.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={dll}
          onChange={(o) => setDll(String(o.data))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={patch}>
          {game.patched ? "Repatch with these settings" : "Patch this game"}
        </ButtonItem>
      </PanelSectionRow>
      {game.patched && (
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={busy} onClick={unpatch}>
            Unpatch this game
          </ButtonItem>
        </PanelSectionRow>
      )}
    </>
  );
}
