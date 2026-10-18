import { useEffect, useState } from "react";
import { ButtonItem, ConfirmModal, DropdownItem, Field, PanelSectionRow, showModal } from "@decky/ui";
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
import { DEFAULT_FSR4_VARIANT, FSR4_VARIANT_OPTIONS, PROXY_DLL_OPTIONS } from "../optiscalerOptions";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";

const POLL_MS = 5000;

function toast(body: string) {
  toaster.toast({ title: "OptiScaler", body });
}

const variantHint = (v: string) => FSR4_VARIANT_OPTIONS.find((o) => o.value === v)?.hint;

export function useOptiStatus() {
  const [status, setStatus] = useState<OptiStatus | null>(null);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      optiscalerStatus()
        .then((s) => !cancelled && setStatus(s))
        .catch(() => undefined);
    load();
    const id = setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);
  return [status, setStatus] as const;
}

// Installing OptiScaler into ~/fgmod, the way Decky Framegen does (and where it finds an install Decky Framegen made).
export function OptiScalerSetup({ status, onChange }: { status: OptiStatus | null; onChange: () => void }) {
  const [variant, setVariant] = useState<string>(DEFAULT_FSR4_VARIANT);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (status?.selected_fsr4_variant) setVariant(status.selected_fsr4_variant);
  }, [status?.selected_fsr4_variant]);
  if (!status) return null;

  const install = async () => {
    setBusy(true);
    try {
      const r = await optiscalerInstall(variant);
      toast(r.status === "success" ? r.output ?? "Installed" : r.message ?? "Install failed");
    } finally {
      setBusy(false);
      onChange();
    }
  };

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
      <PanelSectionRow>
        <DropdownItem
          label="Default FSR4 runtime"
          description={variantHint(variant)}
          rgOptions={FSR4_VARIANT_OPTIONS.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={variant}
          onChange={(o) => setVariant(String(o.data))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" disabled={busy} onClick={install}>
          {busy ? "Working…" : status.exists ? "Reinstall OptiScaler" : "Install OptiScaler"}
        </ButtonItem>
      </PanelSectionRow>
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

export function OptiScalerGame({ appid, status }: { appid: string; status: OptiStatus | null }) {
  const [game, setGame] = useState<OptiGame | null>(null);
  const [dll, setDll] = useState<string>("dxgi.dll");
  const [variant, setVariant] = useState<string>(DEFAULT_FSR4_VARIANT);
  const [busy, setBusy] = useState(false);

  const load = () =>
    optiscalerGameStatus(appid).then((g) => {
      setGame(g);
      if (g.dll_name) setDll(g.dll_name);
      if (g.fsr4_variant) setVariant(g.fsr4_variant);
    });
  useEffect(() => {
    setGame(null);
    load();
  }, [appid]);
  useEffect(() => {
    if (status?.selected_fsr4_variant && !game?.patched) setVariant(status.selected_fsr4_variant);
  }, [status?.selected_fsr4_variant]);

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
      const r = await optiscalerPatchGame(appid, dll, current, variant);
      if (r.status === "success") {
        if (r.launch_options && !writeLaunchOptions(id, r.launch_options)) {
          toast(`Patched, but couldn't set the launch options. Set them in Steam: ${r.launch_options}`);
        } else {
          toast(`${r.message ?? "Patched"} In the game, select DLSS to get FSR / XeSS. Insert opens OptiScaler's menu.`);
        }
      } else {
        toast(r.message ?? "Patching failed");
      }
    } finally {
      setBusy(false);
      load();
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
        <DropdownItem
          label="Proxy DLL"
          description={PROXY_DLL_OPTIONS.find((o) => o.value === dll)?.hint}
          rgOptions={PROXY_DLL_OPTIONS.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={dll}
          onChange={(o) => setDll(String(o.data))}
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <DropdownItem
          label="FSR4 runtime"
          description={variantHint(variant)}
          rgOptions={FSR4_VARIANT_OPTIONS.map((o) => ({ data: o.value, label: o.label }))}
          selectedOption={variant}
          onChange={(o) => setVariant(String(o.data))}
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
