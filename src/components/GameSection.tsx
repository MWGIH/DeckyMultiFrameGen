import { useEffect, useState } from "react";
import { Field, PanelSection, PanelSectionRow, ToggleField } from "@decky/ui";
import { BelowDropdown } from "./BelowDropdown";
import { GAME_NOTES } from "../gameNotes";
import { toaster } from "@decky/api";
import {
  getGame,
  setGameBackend,
  type Backend,
  type GameChoice,
  type GameDetail,
  type Fsr4Status,
  type GameSummary,
  type HelixStatus,
  type OptiStatus,
} from "../api";
import type { SelectedGame } from "../hooks/useSelectedGame";
import {
  hasLauncherSkip,
  LAUNCHER_SKIP_GAMES,
  launcherSkipOn,
  readLaunchOptions,
  setLauncherSkip,
  withLauncherSkip,
  writeLaunchOptions,
} from "../launchOptions";
import { HelixSRGame } from "./HelixSRGame";
import { OptiScalerGame } from "./OptiScaler";
import { MakoGame } from "./MakoGame";
import { HelixInOptiGame } from "./HelixInOpti";
import { Fsr4Game } from "./FSR4Injector";

const CHOICE_LABELS: Record<GameChoice, string> = {
  none: "Off",
  optiscaler: "OptiScaler",
  helixsr: "HelixSR",
  mako: "MAKO",
  "optiscaler+mako": "OptiScaler + MAKO",
  "helixsr+mako": "HelixSR + MAKO",
  "optiscaler+helixsr": "OptiScaler + HelixSR",
  "optiscaler+helixsr+mako": "OptiScaler + HelixSR + MAKO",
  fsr4injector: "FSR4 Injector",
  "fsr4injector+mako": "FSR4 Injector + MAKO",
};

const parts = (choice: GameChoice | null | undefined) =>
  choice ? choice.split("+") : [];

const toast = (body: string) => toaster.toast({ title: "MultiFrameGen", body });

const SOURCE_LABELS = {
  running: "Running now",
  library: "Open in your library",
  picked: "Picked from the list",
};

type Props = {
  selected: SelectedGame;
  games: GameSummary[];
  backends: Backend[] | null;
  helix: HelixStatus | null;
  opti: OptiStatus | null;
  fsr4: Fsr4Status | null;
  onPick: (appid: string) => void;
  onChoice: (choice: GameChoice | null) => void;
};

export function GameSection({
  selected,
  games,
  backends,
  helix,
  opti,
  fsr4,
  onPick,
  onChoice,
}: Props) {
  const [detail, setDetail] = useState<GameDetail | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    if (selected) {
      getGame(selected.appid).then((d) => {
        if (!cancelled) setDetail(d);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [selected?.appid]);
  useEffect(
    () =>
      onChoice(
        detail?.ok && detail.installed ? (detail.backend ?? null) : null,
      ),
    [detail],
  );

  // --launcher-skip in the launch options of games with their own launcher, as soon as the game is shown
  const [skipLauncher, setSkipLauncher] = useState(false);
  const skipGame = Boolean(selected && selected.appid in LAUNCHER_SKIP_GAMES);
  useEffect(() => {
    if (!selected || !skipGame || !detail?.ok || !detail.installed) return;
    const id = Number(selected.appid);
    const on = launcherSkipOn(selected.appid);
    setSkipLauncher(on);
    readLaunchOptions(id).then((current) => {
      if (current !== null && hasLauncherSkip(current) !== on)
        writeLaunchOptions(id, withLauncherSkip(current, on));
    });
  }, [selected?.appid, detail?.ok, detail?.installed]);
  const toggleSkipLauncher = async (on: boolean) => {
    if (!selected) return;
    const id = Number(selected.appid);
    setLauncherSkip(selected.appid, on);
    setSkipLauncher(on);
    const current = await readLaunchOptions(id);
    if (current === null || !writeLaunchOptions(id, withLauncherSkip(current, on)))
      toast(
        `Couldn't change the launch options. ${on ? "Add" : "Remove"} --launcher-skip in Steam.`,
      );
  };

  const [switching, setSwitching] = useState(false);
  const [optiChanged, setOptiChanged] = useState(0);
  // Switching takes the previous choice out of the game (OptiScaler and HelixSR can't both be in it)
  const choose = async (choice: GameChoice) => {
    if (!selected || choice === detail?.backend) return;
    const id = Number(selected.appid);
    setSwitching(true);
    try {
      const current = detail?.installed ? await readLaunchOptions(id) : null;
      const r = await setGameBackend(selected.appid, choice, current);
      if (r.ok) {
        setDetail((d) => (d ? { ...d, backend: choice } : d));
        if (
          r.launch_options != null &&
          !writeLaunchOptions(id, r.launch_options)
        ) {
          toast(
            `Couldn't update the launch options. Set them in Steam: ${r.launch_options || "(empty)"}`,
          );
        }
        if (r.removed?.length)
          toast(`Removed ${r.removed.join(" and ")} from this game.`);
        if (
          parts(choice).includes("mako") &&
          backends?.find((b) => b.id === "mako")?.lossless_scaling === false
        )
          toast(
            "Lossless Scaling isn't installed: MAKO's frame generation needs it. Install it from the Steam Store.",
          );
        if (r.verify_files)
          toast(
            "OptiScaler had replaced some of the game's files. If it doesn't start, verify its files in Steam (Properties, Installed Files).",
          );
        if (r.fsr4)
          toast(
            r.fsr4.ok
              ? "FSR4 Injector is on. Start the game and choose AMD FSR as its upscaler."
              : `FSR4 Injector wasn't put in: ${r.fsr4.error}`,
          );
        if (r.helix_in_opti) {
          toast(
            r.helix_in_opti.ok
              ? "HelixSR added to OptiScaler"
              : `HelixSR wasn't added: ${r.helix_in_opti.error}`,
          );
        }
        setOptiChanged((n) => n + 1);
      } else {
        toast(r.message ?? "Couldn't save the choice");
      }
    } finally {
      setSwitching(false);
    }
  };

  const installed = new Set(
    (backends ?? []).filter((b) => b.installed).map((b) => b.id as string),
  );
  const name =
    detail?.name ?? selected?.name ?? (selected ? `App ${selected.appid}` : "");

  return (
    <PanelSection title="Game">
      {(!selected || selected.source === "picked") && (
        <PanelSectionRow>
          <BelowDropdown
            label="Choose a game"
            description="No game is running or open in your library"
            menuLabel="Installed games"
            strDefaultLabel="Pick a game"
            rgOptions={games.map((g) => ({ data: g.appid, label: g.name }))}
            selectedOption={
              selected?.source === "picked" ? selected.appid : undefined
            }
            onChange={(o) => onPick(String(o.data))}
          />
        </PanelSectionRow>
      )}
      {selected && (
        <>
          <PanelSectionRow>
            <Field label={name} description={SOURCE_LABELS[selected.source]}>
              {detail && !detail.installed ? "Not installed" : null}
            </Field>
          </PanelSectionRow>
          {detail?.ok && GAME_NOTES[selected.appid] && (
            <PanelSectionRow>
              <Field
                label="Tested with this game"
                description={GAME_NOTES[selected.appid]}
              />
            </PanelSectionRow>
          )}
          {detail?.ok && detail.installed && skipGame && (
            <PanelSectionRow>
              <ToggleField
                label="Skip the game's launcher"
                description="Adds --launcher-skip to the launch options so the game starts straight away. Turn it off if you need the launcher, e.g. to change its settings or mods."
                checked={skipLauncher}
                onChange={toggleSkipLauncher}
              />
            </PanelSectionRow>
          )}
          {detail?.ok && (
            <PanelSectionRow>
              <BelowDropdown
                label="Use"
                rgOptions={(detail.choices ?? [])
                  // only methods that are installed, plus whatever the game is set to now
                  .filter(
                    (c) =>
                      c === "none" ||
                      c === detail.backend ||
                      parts(c).every((id) => installed.has(id)),
                  )
                  .map((c) => ({ data: c, label: CHOICE_LABELS[c] }))}
                selectedOption={detail.backend}
                disabled={switching}
                onChange={(o) => choose(o.data as GameChoice)}
              />
            </PanelSectionRow>
          )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("helixsr") &&
            !parts(detail.backend).includes("optiscaler") && (
              <HelixSRGame appid={selected.appid} helix={helix} />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("optiscaler") && (
              <OptiScalerGame
                appid={selected.appid}
                status={opti}
                onChange={() => setOptiChanged((n) => n + 1)}
              />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("optiscaler") &&
            parts(detail.backend).includes("helixsr") && (
              <HelixInOptiGame
                appid={selected.appid}
                helix={helix}
                refresh={optiChanged}
              />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("fsr4injector") && (
              <Fsr4Game
                key={`${selected.appid}:${detail.backend}`}
                appid={selected.appid}
                status={fsr4}
              />
            )}
          {detail?.ok &&
            detail.installed &&
            parts(detail.backend).includes("mako") && (
              <MakoGame
                appid={selected.appid}
                makoInstalled={installed.has("mako")}
                losslessScaling={
                  backends?.find((b) => b.id === "mako")?.lossless_scaling !==
                  false
                }
              />
            )}
        </>
      )}
    </PanelSection>
  );
}
