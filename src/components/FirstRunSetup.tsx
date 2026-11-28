import { useEffect, useState } from "react";
import {
  ButtonItem,
  DialogButton,
  DialogHeader,
  Field,
  Focusable,
  ModalRoot,
  PanelSection,
  PanelSectionRow,
  showModal,
  ToggleField,
} from "@decky/ui";
import { getSetupDone, setSetupDone, type Backend, type HelixStatus } from "../api";
import {
  INSTALL_NAMES,
  INSTALL_ORDER,
  installBackends,
  useInstallState,
  type InstallId,
  type InstallRefresh,
} from "../installs";

// What each backend is for, in words that don't need its name: shown on its switch in the install dialog
export const INSTALL_ABOUT: Record<InstallId, { label: string; about: string; recommended: boolean }> = {
  optiscaler: {
    label: "OptiScaler",
    about:
      "Swaps the game's upscaler for FSR 4 or XeSS and adds frame generation. Works in most games that have DLSS, " +
      "FSR or XeSS.",
    recommended: true,
  },
  fsr4injector: {
    label: "FSR4 Injector",
    about:
      "Upgrades games that already have FSR 3.1 to FSR 4. Downloads about 43 MB from AMD; installing means you " +
      "accept AMD's software licence.",
    recommended: true,
  },
  helixsr: {
    label: "HelixSR",
    about: "Its own upscaler (HLX FSR 4, and HLX DLSS when built). About 280 MB.",
    recommended: true,
  },
  mako: {
    label: "MAKO",
    about: "Frame generation for any game, including games without their own. Needs a restart once installed.",
    recommended: true,
  },
  anrfg: {
    label: "ANR FG",
    about: "Frame generation for DirectX 12 games that offer DLSS frame generation. A closed-source beta, about 11 MB.",
    recommended: false,
  },
};

const BUILD_ABOUT =
  "Needed for HLX DLSS and HelixSR Scaler. Takes a few minutes, needs Proton installed in Steam, and downloads " +
  "NVIDIA's DLSS DLL (NVIDIA's licence applies). Off: only the FSR drop-in (HLX FSR 4), with no build.";

function InstallDialog({
  missing,
  helixBuild,
  intro,
  onInstall,
  closeModal,
}: {
  missing: InstallId[];
  helixBuild: boolean;
  intro: string;
  onInstall: (ids: InstallId[], helixBuild: boolean) => void;
  closeModal?: () => void;
}) {
  const [picked, setPicked] = useState<Set<InstallId>>(
    () => new Set(missing.filter((id) => INSTALL_ABOUT[id].recommended)),
  );
  const [build, setBuild] = useState(helixBuild);
  const toggle = (id: InstallId, on: boolean) => {
    const next = new Set(picked);
    if (on) next.add(id);
    else next.delete(id);
    setPicked(next);
  };
  const ids = missing.filter((id) => picked.has(id));
  const notes: string[] = [];
  if (picked.has("helixsr") && build) notes.push("HelixSR's build takes a few minutes.");
  if (picked.has("helixsr") || picked.has("mako")) notes.push("A restart is asked for at the end.");
  return (
    <ModalRoot onCancel={closeModal} closeModal={closeModal}>
      <DialogHeader>Choose what to install</DialogHeader>
      <Focusable
        flow-children="column"
        style={{ display: "flex", flexDirection: "column", maxHeight: "60vh", overflowY: "auto" }}
      >
        <Field description={intro} bottomSeparator="none" />
        {missing.map((id) => (
          <div key={id}>
            <ToggleField
              label={INSTALL_ABOUT[id].label}
              description={INSTALL_ABOUT[id].about}
              checked={picked.has(id)}
              onChange={(on) => toggle(id, on)}
            />
            {id === "helixsr" && picked.has("helixsr") && (
              <div style={{ paddingLeft: "16px" }}>
                <ToggleField label="Build HelixSR" description={BUILD_ABOUT} checked={build} onChange={setBuild} />
              </div>
            )}
          </div>
        ))}
        <Field
          description={
            ids.length
              ? `Installs ${ids.map((i) => INSTALL_NAMES[i]).join(", ")}. ${notes.join(" ")} Keep the Deck awake ` +
                "until it's done."
              : "Nothing is picked."
          }
          bottomSeparator="none"
        />
      </Focusable>
      <Focusable flow-children="row" style={{ display: "flex", gap: "8px", marginTop: "12px" }}>
        <DialogButton
          disabled={!ids.length}
          onClick={() => {
            closeModal?.();
            onInstall(ids, build);
          }}
        >
          Install
        </DialogButton>
        <DialogButton onClick={closeModal}>Cancel</DialogButton>
      </Focusable>
    </ModalRoot>
  );
}

export function openInstallDialog(
  missing: InstallId[],
  helixBuild: boolean,
  intro: string,
  onInstall: (ids: InstallId[], helixBuild: boolean) => void,
) {
  showModal(<InstallDialog missing={missing} helixBuild={helixBuild} intro={intro} onInstall={onInstall} />);
}

// Backends not installed yet, in the order they're offered
export function missingBackends(backends: Backend[] | null): InstallId[] {
  if (!backends) return [];
  return INSTALL_ORDER.filter((id) => backends.some((b) => b.id === id && !b.installed));
}

// null until known
export function useSetupDone() {
  const [done, setDone] = useState<boolean | null>(null);
  useEffect(() => {
    getSetupDone()
      .then(setDone)
      .catch(() => setDone(true));
  }, []);
  const mark = () => {
    setDone(true);
    setSetupDone(true).catch(() => undefined);
  };
  return [done, mark] as const;
}

type Props = {
  backends: Backend[] | null;
  helix: HelixStatus | null;
  refresh: InstallRefresh;
};

// The Get started card is up: nothing is installed and setup wasn't finished or skipped
export function showGetStarted(backends: Backend[] | null, done: boolean | null): boolean {
  return !!backends && done === false && !backends.some((b) => b.installed);
}

// The first-time setup at the top of the panel while nothing is installed, and "Install more options" afterwards
// (both open the same dialog), so nobody needs the backend list to get started
export function FirstRunSetup({
  backends,
  helix,
  refresh,
  done,
  markDone,
}: Props & { done: boolean | null; markDone: () => void }) {
  const { batch, starting } = useInstallState();
  const missing = missingBackends(backends);
  const busy = !!batch || !!starting;
  const install = (ids: InstallId[], build: boolean) => {
    markDone();
    installBackends(ids, {
      helixBuild: ids.includes("helixsr") ? build : undefined,
      refresh,
    });
  };
  const open = (intro: string) => openInstallDialog(missing, helix?.build !== false, intro, install);

  if (busy || !missing.length || !showGetStarted(backends, done)) return null;
  return (
    <PanelSection title="Get started">
      <PanelSectionRow>
        <Field
          label="Install what MultiFrameGen uses"
          description="Games can't use any upscaler or frame generation until at least one is installed. Pick what to install, and it's set up for you."
          bottomSeparator="none"
        />
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem
          layout="below"
          onClick={() =>
            open("The ticked ones suit most games. You can install the others later with Install more options.")
          }
        >
          Choose what to install
        </ButtonItem>
      </PanelSectionRow>
      <PanelSectionRow>
        <ButtonItem layout="below" onClick={markDone}>
          Not now
        </ButtonItem>
      </PanelSectionRow>
    </PanelSection>
  );
}

// Under the update notice: for whatever isn't installed yet
export function InstallMoreButton({ backends, helix, refresh, markDone }: Props & { markDone: () => void }) {
  const { batch, starting } = useInstallState();
  const missing = missingBackends(backends);
  if (batch || starting || !missing.length) return null;
  return (
    <PanelSectionRow>
      <ButtonItem
        layout="below"
        onClick={() =>
          openInstallDialog(
            missing,
            helix?.build !== false,
            "These aren't installed yet. Tick what you want; removing is in Backends.",
            (ids, build) => {
              markDone();
              installBackends(ids, { helixBuild: ids.includes("helixsr") ? build : undefined, refresh });
            },
          )
        }
      >
        Install more options
      </ButtonItem>
    </PanelSectionRow>
  );
}
