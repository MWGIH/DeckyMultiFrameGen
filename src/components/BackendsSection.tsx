import { useEffect, useState } from "react";
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
  makoGameLaunchOptions,
  makoGames,
  type Backend,
  type Fsr4Status,
  type HelixStatus,
  type OptiStatus,
} from "../api";
import { Fsr4Setup } from "./FSR4Injector";
import { readLaunchOptions, writeLaunchOptions } from "../launchOptions";
import { HelixSRSetup } from "./HelixSRSetup";
import { OptiScalerSetup } from "./OptiScaler";
import { UpdatesCheck } from "./UpdatesCheck";
import { installMako, uninstallMako } from "../mako/api/makoApi";
import { toaster } from "@decky/api";
import { promptRestart } from "../restartPrompt";
import { LosslessWarning } from "./LosslessWarning";

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
};

const COLLAPSED_KEY = "multifg:backendsCollapsed";

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

// One line per backend while the section is hidden, e.g. "OptiScaler 0.9.4 · HelixSR v1.9.3 · MAKO not installed"
function summary(backends: Backend[]): string {
  return backends
    .map(
      (b) =>
        `${b.name} ${b.installed ? (b.version ?? "installed") : "not installed"}`,
    )
    .join(" · ");
}

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
  } = props;
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = () => {
    setCollapsed(!collapsed);
    try {
      localStorage.setItem(COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // just not remembered
    }
  };
  return (
    <PanelSection title="Backends">
      <PanelSectionRow>
        <ToggleField
          label="Show backends"
          checked={!collapsed}
          onChange={toggle}
          description={
            collapsed && backends
              ? summary(backends) +
                (helix?.job?.state === "failed"
                  ? `. HelixSR ${helix.job.tag} setup failed: show backends for its log.`
                  : "")
              : undefined
          }
        />
      </PanelSectionRow>
      {!collapsed && (
        <UpdatesCheck
          optiJobState={opti?.job?.state}
          helixJobState={helix?.job?.state}
          onOptiChange={onOptiChange}
          onHelixChange={onHelixChange}
          onMakoChange={onMakoChange}
          fsr4JobState={fsr4?.job?.state}
          onFsr4Change={onFsr4Change}
        />
      )}
      {collapsed ? null : backends === null ? (
        <PanelSectionRow>
          <Field label="Checking…" />
        </PanelSectionRow>
      ) : (
        backends.map((b) => (
          <div key={b.id}>
            <PanelSectionRow>
              <Field
                label={b.name}
                description={[b.kind, ...(b.notes ?? [])].join("\n")}
                bottomSeparator="standard"
              >
                {statusLine(b)}
              </Field>
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
            {b.id === "mako" && b.lossless_scaling === false && (
              <LosslessWarning />
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
